import gi
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GObject

import asyncio
import enum
import json
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import httpx
from babel import Locale
from diskcache import Cache
from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport

from . import models
from .queries import *

MODEL_CLASSES = {
    'Manga': models.Manga,
    'Chapter': models.Chapter,
    'Category': models.Category,
    'Extension': models.Extension,
    'Source': models.Source,
    'Download': models.Download,
}

FETCH_CONNECTIONS = 8
IMAGE_TIMEOUT = 10
IMAGE_RETRIES = 1
IMAGE_TTL = 30 * 24 * 60 * 60
CACHE_SIZE_LIMIT = 500 * 1024 * 1024
GRAPHQL_TIMEOUT = 20
POLL_INTERVAL = 10
LIBRARY_POLL_TICKS = 3
SOURCE_POLL_TICKS = 30
AUTO_UPDATE_INTERVAL = 30 * 60
AUTO_UPDATE_RETRY = 60
UPDATE_POLL_INTERVAL = 3
LOCAL_SOURCE_ID = "0"
DEFAULT_CATEGORY_ID = 0
THUMB_WIDTH = 300
THUMB_HEIGHT = 450
THUMB_CACHE_ITEMS = 256

READING_MODES = {
    0: ("single", "vertical"),
    1: ("double", "vertical"),
    2: ("webtoon", "vertical"),
    3: ("webtoon", "horizontal"),
    4: ("webtoon", "vertical"),
}
CHAPTER_VARS = {"is_read": "isRead", "is_bookmarked": "isBookmarked", "last_page_read": "lastPageRead"}
FILTER_DEFAULTS = ("checkBoxDefault", "selectDefault", "triStateDefault", "textDefault", "sortDefault")


class SourceMangaType(enum.StrEnum):
    SEARCH = "SEARCH"
    POPULAR = "POPULAR"
    LATEST = "LATEST"


def readingModeValue(mode: str, orientation: str) -> int:
    if mode == "single":
        return 0
    if mode == "double":
        return 1
    if orientation == "horizontal":
        return 3
    return 4


def makeClient(url: str) -> Client:
    transport = AIOHTTPTransport(timeout=GRAPHQL_TIMEOUT, url=url.rstrip('/') + '/api/graphql')
    return Client(transport=transport, fetch_schema_from_transport=False)


def watch(widget, obj: GObject.Object, callback, signal: str = "items-changed"):
    def on_signal(*args):
        callback()

    def on_unrealize(*args):
        GObject.Object.disconnect(obj, handler)

    handler = obj.connect(signal, on_signal)
    widget.connect("unrealize", on_unrealize)


class Suwayomi(GObject.Object):
    __gtype_name__ = 'KaoriIntegrationSuwayomi'

    MODE_KEY = "webUI_readingMode"
    DIRECTION_KEY = "webUI_readingDirection"
    LANGUAGES_KEY = "webUI_browseLanguages"

    url = GObject.Property(type=str, default="http://localhost:4567")
    downloader_state = GObject.Property(type=str, default="STOPPED")
    download_queue = GObject.Property(type=Gio.ListStore)
    library = GObject.Property(type=Gio.ListStore)
    category_revision = GObject.Property(type=int, default=0)

    def __init__(self):
        super().__init__()
        self.loaded_models = {}
        self.pending = {}
        self.closing = set()
        self.session = None
        self.poller = None
        self.updater = None
        self.updating = False
        self.connect_lock = asyncio.Lock()
        self.client = makeClient(self.url)

        image_transport = httpx.AsyncHTTPTransport(
            retries=IMAGE_RETRIES,
            limits=httpx.Limits(max_connections=FETCH_CONNECTIONS),
        )
        self.http = httpx.AsyncClient(
            transport=image_transport,
            timeout=httpx.Timeout(IMAGE_TIMEOUT, pool=None),
            follow_redirects=True,
        )

        cache_folder = Path(GLib.get_user_cache_dir()) / "kaori" / "images"
        self.cache = Cache(
            str(cache_folder),
            size_limit=CACHE_SIZE_LIMIT,
            eviction_policy="least-recently-used",
        )

        worker_count = max(2, min(4, os.cpu_count() or 2))
        self.decoder = ThreadPoolExecutor(max_workers=worker_count)

        self.thumbs = OrderedDict()
        self.category_members = {}

        self.download_queue = Gio.ListStore(item_type=models.Download)
        self.library = Gio.ListStore(item_type=models.Manga)
        self.categories = Gio.ListStore(item_type=models.Category)
        self.sources = Gio.ListStore(item_type=models.Source)
        self.all_sources = Gio.ListStore(item_type=models.Source)
        self.extensions = Gio.ListStore(item_type=models.Extension)

        self.languages = ["en", "all"]

    def swapClient(self, url: str) -> Client | None:
        self.stopPolling()
        old_client = self.client
        was_connected = self.session is not None
        self.session = None
        self.url = url
        self.client = makeClient(url)
        if was_connected:
            return old_client
        return None

    def reconnect(self, url: str):
        old_client = self.swapClient(url)
        if old_client is not None:
            task = asyncio.create_task(old_client.close_async())
            self.closing.add(task)
            task.add_done_callback(self.closing.discard)

    async def disconnect(self):
        old_client = self.swapClient(self.url)
        if old_client is not None:
            await old_client.close_async()

    async def close(self):
        self.stopPolling()
        if self.session is not None:
            await self.client.close_async()
        await asyncio.gather(*self.closing)
        await self.http.aclose()
        self.decoder.shutdown()
        self.cache.close()

    def startPolling(self):
        if self.poller is None:
            self.poller = asyncio.create_task(self.poll())
        if self.updater is None:
            self.updater = asyncio.create_task(self.autoUpdate())

    def stopPolling(self):
        if self.poller:
            self.poller.cancel()
            self.poller = None
        if self.updater:
            self.updater.cancel()
            self.updater = None

    async def poll(self):
        ticks = 0
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            ticks += 1
            jobs = [self.getDownloadStatus()]
            if ticks % LIBRARY_POLL_TICKS == 0:
                jobs.append(self.refreshLibrary())
            if ticks % SOURCE_POLL_TICKS == 0:
                jobs.append(self.refreshSources())
            await asyncio.gather(*jobs, return_exceptions=True)

    async def autoUpdate(self):
        while True:
            try:
                await self.updateLibrary()
                delay = AUTO_UPDATE_INTERVAL
            except Exception as error:
                print(f"library update failed: {error}")
                delay = AUTO_UPDATE_RETRY
            await asyncio.sleep(delay)

    async def getSession(self):
        async with self.connect_lock:
            if self.session is None:
                self.session = await self.client.connect_async()
        return self.session

    async def query(self, gql_query, variable_values=None) -> dict:
        session = await self.getSession()
        return await session.execute(gql_query, variable_values=variable_values)

    def forget(self, key, entry):
        if self.pending.get(key) is entry:
            del self.pending[key]

    async def shared(self, key, factory):
        entry = self.pending.get(key)
        if entry is None:
            task = asyncio.create_task(factory())
            entry = {"task": task, "waiters": 0}
            self.pending[key] = entry
            task.add_done_callback(lambda finished: self.forget(key, entry))

        entry["waiters"] += 1
        try:
            return await asyncio.shield(entry["task"])
        finally:
            entry["waiters"] -= 1
            if entry["waiters"] == 0 and not entry["task"].done():
                self.forget(key, entry)
                entry["task"].cancel()

    @staticmethod
    def replace(store: Gio.ListStore, items: list):
        if list(store) != items:
            store.splice(0, store.get_n_items(), items)

    async def loadBytes(self, url: str) -> bytes:
        data = await asyncio.to_thread(self.cache.get, url)
        if data is None:
            response = await self.http.get(url)
            response.raise_for_status()
            data = response.content
            await asyncio.to_thread(self.cache.set, url, data, expire=IMAGE_TTL)
        return data

    @staticmethod
    def decode(raw: bytes) -> Gdk.Paintable:
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(raw))

    @staticmethod
    def decodeThumbnail(raw: bytes) -> Gdk.Paintable:
        try:
            stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(raw))
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(stream, THUMB_WIDTH, THUMB_HEIGHT, True, None)
            return Gdk.Texture.new_for_pixbuf(pixbuf)
        except GLib.Error:
            return Gdk.Texture.new_from_bytes(GLib.Bytes.new(raw))

    async def getPaintable(self, url: str) -> Gdk.Paintable:
        raw = await self.shared(('bytes', url), lambda: self.loadBytes(url))
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.decoder, self.decode, raw)

    def cachedThumbnail(self, url: str):
        texture = self.thumbs.get(url)
        if texture is not None:
            self.thumbs.move_to_end(url)
        return texture

    async def getThumbnail(self, url: str) -> Gdk.Paintable:
        texture = self.cachedThumbnail(url)
        if texture is not None:
            return texture
        raw = await self.shared(('bytes', url), lambda: self.loadBytes(url))
        loop = asyncio.get_running_loop()
        texture = await loop.run_in_executor(self.decoder, self.decodeThumbnail, raw)
        self.thumbs[url] = texture
        while len(self.thumbs) > THUMB_CACHE_ITEMS:
            self.thumbs.popitem(last=False)
        return texture

    async def loadThumbnail(self, item):
        try:
            item.paintable = await self.getThumbnail(item.thumbnail_url)
        except Exception as error:
            print(f"thumbnail failed: {item.thumbnail_url}: {error}")

    def startThumbnail(self, item):
        if item.paintable is not None or not item.thumbnail_url:
            return None
        cached = self.cachedThumbnail(item.thumbnail_url)
        if cached is not None:
            item.paintable = cached
            return None
        return asyncio.create_task(self.loadThumbnail(item))

    def getModel(self, model_id: int | str, item_type: str) -> GObject.Object | None:
        return self.loaded_models.get((item_type, model_id))

    def modelFor(self, item_type: str, item_id: int | str) -> GObject.Object:
        key = (item_type, item_id)
        if key not in self.loaded_models:
            self.loaded_models[key] = MODEL_CLASSES[item_type]()
        return self.loaded_models[key]

    def makeModel(self, item: dict | None, item_type: str) -> GObject.Object | None:
        if item is None:
            return None
        if item_type == 'Extension':
            model_id = item['pkgName']
        else:
            model_id = item['id']
        model = self.modelFor(item_type, model_id)
        fill = getattr(self, f"fill{item_type}")
        fill(model, item)
        return model

    def makeModels(self, nodes: list, item_type: str) -> list:
        return [self.makeModel(node, item_type) for node in nodes]

    def makeChapterStore(self, chapter_models: list) -> Gio.ListStore:
        store = Gio.ListStore(item_type=models.Chapter)
        store.splice(0, 0, chapter_models)
        return store

    def absoluteUrl(self, path: str | None) -> str:
        if path:
            return urljoin(self.url, path)
        return ""

    def fillManga(self, model, item: dict):
        model.update_data(
            id=item.get('id'),
            title=item.get('title'),
            author=item.get('author'),
            artist=item.get('artist'),
            description=item.get('description'),
            genre=item.get('genre', []),
            status=item.get('status'),
            initialized=item.get('initialized', False),
            in_library=item.get('inLibrary', False),
            unread_count=item.get('unreadCount', 0),
            first_unread_chapter=self.makeModel(item.get('firstUnreadChapter'), 'Chapter'),
            last_read_chapter=self.makeModel(item.get('lastReadChapter'), 'Chapter'),
            real_url=item.get('realUrl'),
            thumbnail_url=self.absoluteUrl(item.get('thumbnailUrl')),
        )
        chapters = item.get('chapters')
        if chapters:
            if 'totalCount' in chapters:
                model.total_chapters = chapters['totalCount']
            if 'nodes' in chapters:
                chapter_models = self.makeModels(chapters['nodes'], 'Chapter')
                self.replace(model.chapters, chapter_models)

    def fillChapter(self, model, item: dict):
        values = {}
        for key, name in CHAPTER_FIELDS.items():
            if key in item:
                values[name] = item[key]
        model.update_data(id=item['id'], **values)

    def fillCategory(self, model, item: dict):
        model.update_data(
            id=item['id'],
            name=item['name'],
            order=item.get('order', 0),
            is_default=item.get('default', False),
            manga_count=item.get('mangaCount', 0),
        )

    def fillExtension(self, model, item: dict):
        values = {}
        for key, name in EXTENSION_FIELDS.items():
            if key in item:
                values[name] = item[key]
        if 'iconUrl' in item:
            values['icon_url'] = self.absoluteUrl(item['iconUrl'])
        model.update_data(pkg_name=item['pkgName'], **values)

    def fillSource(self, model, item: dict):
        extension = item.get('extension') or {}
        model.update_data(
            id=item['id'],
            name=item['name'],
            lang=item.get('lang', ''),
            icon_url=self.absoluteUrl(item.get('iconUrl')),
            is_configurable=item.get('isConfigurable', False),
            is_nsfw=item.get('isNsfw', False),
            extension_pkg_name=extension.get('pkgName', ''),
            extension_name=extension.get('name', ''),
        )

    async def getManga(self, manga_id: int, force: bool = False) -> models.Manga:
        model = self.getModel(manga_id, 'Manga')
        if model and model.initialized and not force:
            return model
        return await self.shared(('manga', manga_id), lambda: self.fetchManga(manga_id))

    async def refreshManga(self, manga_id: int) -> models.Manga:
        return await self.getManga(manga_id, force=True)

    async def fetchManga(self, manga_id: int) -> models.Manga:
        variables = {"id": manga_id, "fetchManga": True, "fetchChapters": True}
        result = await self.query(FETCH_MANGA, variables)
        data = result['fetchMangaAndChapters']
        chapters = data['chapters']
        node = dict(data['manga'])
        node['chapters'] = {'nodes': chapters, 'totalCount': len(chapters)}
        return self.makeModel(node, 'Manga')

    async def getChapters(self, manga_id: int, first: int | None = None, after: str | None = None) -> list:
        variables = {"mangaId": manga_id, "first": first, "after": after}
        result = await self.query(GET_CHAPTERS_MANGA, variables)
        connection = result['chapters']
        chapter_models = self.makeModels(connection['nodes'], 'Chapter')
        model = self.getModel(manga_id, 'Manga')
        if model:
            self.replace(model.chapters, chapter_models)
            model.total_chapters = connection['totalCount']
        return chapter_models

    async def refreshLibrary(self):
        await self.shared('library', self.loadLibrary)

    async def loadLibrary(self):
        results = await asyncio.gather(self.query(GET_LIBRARY), self.query(GET_CATEGORIES))
        library_result = results[0]
        category_result = results[1]

        manga_models = []
        for index, node in enumerate(library_result['mangas']['nodes']):
            manga_models.append(self.makeModel(node, 'Manga'))
            if index % 200 == 199:
                await asyncio.sleep(0)

        self.buildCategories(category_result['categories']['nodes'], manga_models)

        kept = set(manga_models)
        for model in list(self.library):
            if model not in kept:
                model.in_library = False
        self.replace(self.library, manga_models)

    def buildCategories(self, nodes: list, manga_models: list):
        members = {}
        category_models = []
        assigned = set()

        for node in sorted(nodes, key=lambda node: node['order']):
            if node['id'] == DEFAULT_CATEGORY_ID:
                continue
            ids = set(manga['id'] for manga in node['mangas']['nodes'])
            assigned = assigned | ids
            members[node['id']] = ids
            node_data = dict(node)
            node_data['mangaCount'] = len(ids)
            category_models.append(self.makeModel(node_data, 'Category'))

        default_ids = set(manga.id for manga in manga_models) - assigned
        if default_ids:
            members[DEFAULT_CATEGORY_ID] = default_ids
            default_data = {
                'id': DEFAULT_CATEGORY_ID,
                'name': 'Default',
                'order': 0,
                'default': True,
                'mangaCount': len(default_ids),
            }
            category_models.insert(0, self.makeModel(default_data, 'Category'))

        changed = members != self.category_members
        self.category_members = members
        self.replace(self.categories, category_models)
        if changed:
            self.category_revision += 1

    async def updateLibrary(self):
        if self.updating:
            return
        self.updating = True
        try:
            await self.query(UPDATE_LIBRARY, {"categories": None})
            while True:
                await asyncio.sleep(UPDATE_POLL_INTERVAL)
                result = await self.query(GET_LIBRARY_UPDATE_STATUS)
                if not result['libraryUpdateStatus']['jobsInfo']['isRunning']:
                    break
        finally:
            self.updating = False
        await self.refreshLibrary()

    def syncLibraryMembership(self, model: models.Manga, in_library: bool):
        found, position = self.library.find(model)
        if in_library and not found:
            self.library.append(model)
        elif not in_library and found:
            self.library.remove(position)

    async def refreshExtensions(self):
        await self.shared('extensions', self.loadExtensions)

    async def loadExtensions(self):
        result = await self.query(FETCH_EXTENSIONS)
        extension_models = self.makeModels(result['fetchExtensions']['extensions'], 'Extension')
        self.replace(self.extensions, extension_models)

    async def refreshSources(self):
        await self.shared('sources', self.loadSources)

    async def loadSources(self):
        results = await asyncio.gather(self.query(GET_SOURCES), self.getBrowseLanguages())
        sources_result = results[0]
        source_models = self.makeModels(sources_result['sources']['nodes'], 'Source')
        self.replace(self.all_sources, source_models)
        self.applyLanguages()

    def applyLanguages(self):
        visible_sources = []
        for source in self.all_sources:
            if source.lang in self.languages or source.id == LOCAL_SOURCE_ID:
                visible_sources.append(source)
        self.replace(self.sources, visible_sources)

    async def getBrowseLanguages(self):
        values = await self.getGlobalMetaValues()
        languages = self.readMeta(values, self.LANGUAGES_KEY)
        if languages is not None:
            self.languages = languages

    async def setBrowseLanguages(self, languages: list):
        self.languages = languages
        self.applyLanguages()
        await self.setGlobalMeta(self.LANGUAGES_KEY, languages)

    async def getSourceManga(
        self,
        source_id: str,
        fetch_type: SourceMangaType = SourceMangaType.POPULAR,
        page: int = 1,
        query: str | None = None,
        filters: list | None = None,
    ) -> list:
        result = await self.query(GET_SOURCE_MANGA, {
            "source": source_id,
            "type": fetch_type,
            "page": page,
            "query": query,
            "filters": filters or None,
        })
        return self.makeModels(result['fetchSourceManga']['mangas'], 'Manga')

    def makeFilter(self, node: dict) -> dict:
        default = None
        for key in FILTER_DEFAULTS:
            if key in node:
                default = node[key]
                break

        children = []
        for child in node.get("filters") or []:
            children.append(self.makeFilter(child))

        return {
            "type": node.get("type"),
            "name": node.get("name") or "",
            "default": default,
            "values": node.get("values") or [],
            "filters": children,
        }

    async def getSourceFilters(self, source_id: str) -> list:
        result = await self.query(GET_SOURCE_FILTERS, {"id": source_id})
        return [self.makeFilter(node) for node in result['source']['filters']]

    async def changeExtension(self, pkg_name: str, **patch):
        model = self.getModel(pkg_name, 'Extension')
        model.is_busy = True
        result = await self.query(UPDATE_EXTENSION, {"pkgName": pkg_name, **patch})
        self.makeModel(result['updateExtension']['extension'], 'Extension')
        await self.refreshSources()
        model.is_busy = False

    async def installExtension(self, pkg_name: str):
        await self.changeExtension(pkg_name, install=True)

    async def updateExtension(self, pkg_name: str):
        await self.changeExtension(pkg_name, update=True)

    async def uninstallExtension(self, pkg_name: str):
        await self.changeExtension(pkg_name, uninstall=True)

    def makePageModel(self, chapter_id: int, index: int, url: str) -> models.Page:
        return models.Page(index=index, chapter_id=chapter_id, url=self.absoluteUrl(url))

    async def getChapterPages(self, chapter_id: int) -> list:
        result = await self.query(FETCH_CHAPTER_PAGES, {"chapterId": chapter_id})
        data = result['fetchChapterPages']
        chapter = data['chapter']
        manga = chapter['manga']

        chapter_model = self.getModel(chapter_id, 'Chapter')
        chapter_model.update_data(
            page_count=chapter['pageCount'],
            is_downloaded=chapter['isDownloaded'],
        )
        manga_model = self.getModel(manga['id'], 'Manga')
        manga_model.download_count = manga['downloadCount']

        pages = []
        for index, url in enumerate(data['pages']):
            pages.append(self.makePageModel(chapter_id, index, url))
        return pages

    async def updateChapter(self, chapter_id: int, **changes):
        self.getModel(chapter_id, 'Chapter').update_data(**changes)

        variables = {"id": chapter_id}
        for name, value in changes.items():
            variables[CHAPTER_VARS[name]] = value

        result = await self.query(UPDATE_CHAPTER, variables)
        node = result['updateChapter']['chapter']
        self.makeModel(node, 'Chapter')
        manga_model = self.getModel(node['manga']['id'], 'Manga')
        manga_model.unread_count = node['manga']['unreadCount']

    async def deleteDownloadedChapter(self, chapter_id: int):
        self.getModel(chapter_id, 'Chapter').is_downloaded = False

        result = await self.query(DELETE_DOWNLOADED_CHAPTER, {"id": chapter_id})
        node = result['deleteDownloadedChapter']['chapters']
        self.makeModel(node, 'Chapter')
        manga_model = self.getModel(node['manga']['id'], 'Manga')
        manga_model.download_count = node['manga']['downloadCount']

    async def setMangaLibrary(self, manga_id: int, in_library: bool):
        model = self.getModel(manga_id, 'Manga')
        model.in_library = in_library
        self.syncLibraryMembership(model, in_library)

        result = await self.query(SET_MANGA_LIBRARY, {"id": manga_id, "inLibrary": in_library})
        node = result['updateManga']['manga']
        model.update_data(in_library_at=node['inLibraryAt'], unread_count=node['unreadCount'])

        if in_library:
            await self.refreshLibrary()

    async def addToLibrary(self, manga_id: int):
        await self.setMangaLibrary(manga_id, True)

    async def removeFromLibrary(self, manga_id: int):
        await self.setMangaLibrary(manga_id, False)

    def makeDownloadModel(self, item: dict) -> models.Download:
        chapter = item['chapter']
        manga = item['manga']
        model = self.modelFor('Download', chapter['id'])
        model.update_data(
            chapter_id=chapter['id'],
            chapter_name=chapter['name'],
            manga_id=manga['id'],
            manga_title=manga['title'],
            progress=item['progress'],
            state=item['state'],
            tries=item['tries'],
        )
        return model

    async def getDownloadStatus(self):
        result = await self.query(GET_DOWNLOAD_STATUS)
        status = result['downloadStatus']
        self.downloader_state = status['state']

        new_queue = [self.makeDownloadModel(item) for item in status['queue']]

        finished_manga_ids = set()
        for download in list(self.download_queue):
            if download not in new_queue:
                finished_manga_ids.add(download.manga_id)

        self.replace(self.download_queue, new_queue)

        refreshes = [self.getChapters(manga_id) for manga_id in finished_manga_ids]
        await asyncio.gather(*refreshes)

    async def downloadCommand(self, gql_query, variables=None):
        await self.query(gql_query, variables)
        await self.getDownloadStatus()

    async def enqueueChapterDownload(self, chapter_id: int):
        await self.downloadCommand(ENQUEUE_CHAPTER_DOWNLOAD, {"id": chapter_id})

    async def dequeueChapterDownload(self, chapter_id: int):
        await self.downloadCommand(DEQUEUE_CHAPTER_DOWNLOAD, {"id": chapter_id})

    async def reorderChapterDownload(self, chapter_id: int, to: int):
        await self.downloadCommand(REORDER_CHAPTER_DOWNLOAD, {"chapterId": chapter_id, "to": to})

    async def clearDownloader(self):
        await self.downloadCommand(CLEAR_DOWNLOADER)

    async def startDownloader(self):
        await self.downloadCommand(START_DOWNLOADER)

    async def stopDownloader(self):
        await self.downloadCommand(STOP_DOWNLOADER)

    @staticmethod
    def metaValues(nodes: list) -> dict:
        values = {}
        for meta in nodes:
            values[meta['key']] = meta['value']
        return values

    def readMeta(self, values: dict, key: str):
        value = values.get(key)
        if value:
            return json.loads(value)
        return None

    def parseReaderSettings(self, values: dict) -> dict:
        settings = {}

        mode = self.readMeta(values, self.MODE_KEY)
        if mode is not None:
            mode_name, orientation = READING_MODES[mode]
            settings["mode"] = mode_name
            settings["orientation"] = orientation

        direction = self.readMeta(values, self.DIRECTION_KEY)
        if direction is not None:
            if direction == 1:
                settings["direction"] = "rtl"
            else:
                settings["direction"] = "ltr"

        return settings

    async def getGlobalMetaValues(self) -> dict:
        result = await self.query(GET_GLOBAL_READER_META)
        return self.metaValues(result['metas']['nodes'])

    async def getReaderSettings(self, manga_id: int) -> dict:
        result = await self.query(GET_READER_META, {"id": manga_id})
        values = self.metaValues(result['metas']['nodes'])
        values.update(self.metaValues(result['manga']['meta']))
        return self.parseReaderSettings(values)

    async def setReaderSettings(self, manga_id: int, settings: dict):
        mode_value = readingModeValue(settings["mode"], settings["orientation"])
        direction_value = 1 if settings["direction"] == "rtl" else 0
        await asyncio.gather(
            self.setMeta(manga_id, self.MODE_KEY, mode_value),
            self.setMeta(manga_id, self.DIRECTION_KEY, direction_value),
        )

    async def setMeta(self, manga_id: int, key: str, value):
        variables = {"mangaId": manga_id, "key": key, "value": json.dumps(value)}
        await self.query(SET_MANGA_META, variables)

    async def getGlobalReaderSettings(self) -> dict:
        values = await self.getGlobalMetaValues()
        return self.parseReaderSettings(values)

    async def setGlobalReadingMode(self, mode: str, orientation: str):
        await self.setGlobalMeta(self.MODE_KEY, readingModeValue(mode, orientation))

    async def setGlobalReadingDirection(self, direction: str):
        await self.setGlobalMeta(self.DIRECTION_KEY, 1 if direction == "rtl" else 0)

    async def setGlobalMeta(self, key: str, value):
        await self.query(SET_GLOBAL_META, {"key": key, "value": json.dumps(value)})

    async def getServerSettings(self) -> dict:
        result = await self.query(GET_SERVER_SETTINGS)
        return result['settings']

    async def setServerSettings(self, **settings):
        await self.query(SET_SERVER_SETTINGS, {"settings": settings})

    async def setDownloadAsCbz(self, value: bool):
        await self.setServerSettings(downloadAsCbz=value)

    async def setDownloadsPath(self, path: str):
        await self.setServerSettings(downloadsPath=path)

    async def getExtensionStores(self) -> list:
        result = await self.query(GET_EXTENSION_STORES)
        return result['extensionStores']['nodes']

    async def addExtensionStore(self, index_url: str) -> dict:
        result = await self.query(ADD_EXTENSION_STORE, {"indexUrl": index_url})
        await self.loadExtensions()
        return result['addExtensionStore']['extensionStore']

    async def removeExtensionStore(self, index_url: str):
        await self.query(REMOVE_EXTENSION_STORE, {"indexUrl": index_url})
        await self.loadExtensions()

    def languageTitle(self, lang: str) -> str:
        if lang == "all":
            return "All languages"
        if not lang or lang == "localsourcelang":
            return "Other"
        try:
            return Locale.parse(lang, sep="-").get_display_name("en")
        except Exception:
            return lang.upper()
