import gi
from gi.repository import GObject, GLib, Gdk, Gio
gi.require_version('Gly', '2')
gi.require_version('GlyGtk4', '2')
from gi.repository import Gly, GlyGtk4

import asyncio
import httpx
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from diskcache import Cache
from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport
from . import models
from .queries import *

from urllib.parse import urljoin

MODEL_CLASSES = {
    'Manga': models.Manga,
    'Chapter': models.Chapter,
    'Extension': models.Extension,
    'Source': models.Source,
}

class SourceMangaType:
    SEARCH = "SEARCH"
    POPULAR = "POPULAR"
    LATEST = "LATEST"


READING_MODES = {
    0: ("single", "vertical"),
    1: ("double", "vertical"),
    2: ("webtoon", "vertical"),
    3: ("webtoon", "horizontal"),
    4: ("webtoon", "vertical"),
}

GLOBAL_MODE_VALUES = {"single": 0, "double": 1}

class Suwayomi(GObject.Object):
    __gtype_name__ = 'KaghezIntegrationSuwayomi'

    url = GObject.Property(type=str, default="http://localhost:4567")
    downloader_state = GObject.Property(type=str, default="STOPPED")
    download_queue = GObject.Property(type=Gio.ListStore)
    library = GObject.Property(type=Gio.ListStore)

    def __init__(self):
        super().__init__()
        self.loaded_models = {}
        transport = AIOHTTPTransport(timeout=20, url=self.get_property('url').rstrip('/') + '/api/graphql')
        self.client = Client(transport=transport, fetch_schema_from_transport=False)
        self.session = None
        self.connect_lock = asyncio.Lock()
        self.http = httpx.AsyncClient()

        self.MODE_KEY = "webUI_readingMode"
        self.DIRECTION_KEY = "webUI_readingDirection"

        self.image_semaphore = asyncio.Semaphore(5)
        self.decode_semaphore = asyncio.Semaphore(2)

        self.cache = Cache(
            str(Path(GLib.get_user_cache_dir()) / "kaghez" / "images"),
            size_limit=500 * 1024 * 1024,
            eviction_policy="least-recently-used",
        )
        self.pending = {}
        self.cache_executor = ThreadPoolExecutor(max_workers=1)

        self.download_queue = Gio.ListStore.new(item_type=models.Download)
        self.library = Gio.ListStore.new(item_type=models.Manga)
        self.sources = Gio.ListStore.new(item_type=models.Source)
        self.extensions = Gio.ListStore.new(item_type=models.Extension)

    def reconnect(self, url: str):
        self.session = None
        self.set_property('url', url)
        transport = AIOHTTPTransport(timeout=20, url=url.rstrip('/') + '/api/graphql')
        self.client = Client(transport=transport, fetch_schema_from_transport=False)

    async def close(self):
        await self.http.aclose()
        self.cache_executor.shutdown(wait=True)
        self.cache.close()
        if self.session is not None:
            await self.client.close_async()
            self.session = None

    async def getSession(self):
        """Lazily connect once, then reuse the same session for every query."""
        if self.session is None:
            async with self.connect_lock:
                if self.session is None:  # re-check after acquiring the lock
                    self.session = await self.client.connect_async()
        return self.session

    async def query(self, gql_query, variable_values=None, raise_errors=False, retries=1) -> dict:
        for attempt in range(retries + 1):
            try:
                session = await self.getSession()
                return await session.execute(gql_query, variable_values=variable_values) or {}
            except (asyncio.TimeoutError, TimeoutError) as e:
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                print(f"[query] timed out after {attempt + 1} attempt(s)")
                if raise_errors:
                    raise
                return {}
            except Exception as e:
                print(f"[query] request failed: {type(e).__name__}: {e}")
                if raise_errors:
                    raise
                return {}
        return {}

    async def shared(self, key, factory):
        if key not in self.pending:
            task = asyncio.create_task(factory())
            task.add_done_callback(lambda done: self.pending.pop(key, None))
            self.pending[key] = task
        return await asyncio.shield(self.pending[key])


    async def getPaintableBytes(self, url: str, retries: int = 1) -> bytes | None:
        for attempt in range(retries + 1):
            try:
                response = await self.http.get(url, timeout=10)
            except httpx.HTTPError as e:
                if attempt < retries:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                print(f"[getPaintableBytes] request failed for {url}: {type(e).__name__}: {e}")
                return None
            if response.status_code != 200:
                print(f"[getPaintableBytes] status {response.status_code} for {url}")
                return None
            return response.content
        return None

    async def getPaintable(self, url: str) -> Gdk.Paintable | None:
        raw_bytes = await self.shared(('bytes', url), lambda: self.loadBytes(url))
        if not raw_bytes:
            return None

        async with self.decode_semaphore:
            try:
                return await asyncio.to_thread(self.makeTexture, raw_bytes)
            except GLib.Error as e:
                print(f"[getPaintable] decode failed for {url}: {e.message}")
                self.cache_executor.submit(self.cache.delete, url)
                return None

    async def loadBytes(self, url: str) -> bytes | None:
        raw_bytes = await asyncio.to_thread(self.cache.get, url)
        if raw_bytes is None:
            async with self.image_semaphore:
                raw_bytes = await self.getPaintableBytes(url)
            if not raw_bytes:
                print(f"[getPaintable] no bytes for {url}")
                return None
            self.cache_executor.submit(self.cache.set, url, raw_bytes)
        return raw_bytes

    def makeTexture(self, raw_bytes: bytes) -> Gdk.Texture:
        gbytes = GLib.Bytes.new(raw_bytes)
        try:
            return Gdk.Texture.new_from_bytes(gbytes)
        except GLib.Error:
            loader = Gly.Loader.new_for_bytes(gbytes)
            frame = loader.load().next_frame()
            return GlyGtk4.frame_get_texture(frame)


    def getModel(self, model_id: int | str, item_type: str) -> GObject.Object | None:
        return self.loaded_models.get((item_type, model_id))

    def makeModel(self, item: dict, item_type: str) -> GObject.Object | None:
        if item is None:
            return None
        item_id = item.get('pkgName') if item_type == 'Extension' else item.get('id')
        if item_id is None:
            return None

        key = (item_type, item_id)
        model = self.loaded_models.get(key)
        if model is None:
            model = MODEL_CLASSES[item_type]()
            self.loaded_models[key] = model

        if item_type == 'Manga':
            self.fillManga(model, item)
        elif item_type == 'Chapter':
            self.fillChapter(model, item)
        elif item_type == 'Extension':
            self.fillExtension(model, item)
        elif item_type == 'Source':
            self.fillSource(model, item)
        return model

    def makeChapterStore(self, chapter_models: list) -> Gio.ListStore:
        store = Gio.ListStore.new(item_type=models.Chapter)
        store.splice(0, 0, chapter_models)
        return store

    def fillManga(self, model, item: dict):
        thumbnail_url = item.get('thumbnailUrl')
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
            thumbnail_url=urljoin(self.url, thumbnail_url) if thumbnail_url else "",
        )

        chapters = item.get('chapters')
        if chapters is not None:
            if 'totalCount' in chapters:
                model.set_property('total_chapters', chapters['totalCount'])
            nodes = chapters.get('nodes')
            if nodes is not None:
                chapter_models = [self.makeModel(node, 'Chapter') for node in nodes]
                model.set_property('chapters', self.makeChapterStore([c for c in chapter_models if c is not None]))
        if model.chapters is None:
            model.set_property('chapters', self.makeChapterStore([]))

    def fillChapter(self, model, item: dict):
        values = {name: item[key] for key, name in CHAPTER_FIELDS.items() if key in item}
        model.update_data(id=item.get('id'), **values)

    def fillExtension(self, model, item: dict):
        values = {name: item[key] for key, name in EXTENSION_FIELDS.items() if key in item}
        if 'iconUrl' in item:
            icon_url = item.get('iconUrl')
            values['icon_url'] = urljoin(self.url, icon_url) if icon_url else ""
        model.update_data(pkg_name=item.get('pkgName'), **values)

    def fillSource(self, model, item: dict):
        icon_url = item.get('iconUrl')
        extension = item.get('extension') or {}
        model.update_data(
            id=item.get('id'),
            name=item.get('name'),
            lang=item.get('lang', ''),
            icon_url=urljoin(self.url, icon_url) if icon_url else "",
            is_configurable=item.get('isConfigurable', False),
            is_nsfw=item.get('isNsfw', False),
            extension_pkg_name=extension.get('pkgName', ''),
            extension_name=extension.get('name', ''),
        )


    async def getManga(self, manga_id: int) -> models.Manga | None:
        model = self.getModel(manga_id, 'Manga')
        if model and model.initialized:
            return model
        return await self.shared(('manga', manga_id), lambda: self.fetchManga(manga_id))

    async def fetchManga(self, manga_id: int) -> models.Manga | None:
        result = await self.query(
            FETCH_MANGA,
            variable_values={"id": manga_id, "fetchManga": True, "fetchChapters": True},
        )
        data = result.get('fetchMangaAndChapters', {})
        node = data.get('manga')
        if node is None:
            return self.getModel(manga_id, 'Manga')  # fall back to whatever is cached
        chapters_list = data.get('chapters', [])
        node = {**node, 'chapters': {'nodes': chapters_list, 'totalCount': len(chapters_list)}}
        return self.makeModel(node, 'Manga')

    async def getChapters(
        self,
        manga_id: int,
        first: int | None = None,
        after: str | None = None,
    ) -> list:
        variables = {"mangaId": manga_id, "first": first, "after": after}
        result = await self.query(GET_CHAPTERS_MANGA, variable_values=variables)
        connection = result.get('chapters', {})
        nodes = connection.get('nodes', [])
        chapter_models = [self.makeModel(node, 'Chapter') for node in nodes]
        chapter_models = [c for c in chapter_models if c is not None]

        model = self.getModel(manga_id, 'Manga')
        if model is not None:
            model.set_property('chapters', self.makeChapterStore(chapter_models))
            model.set_property('total_chapters', connection.get('totalCount', len(chapter_models)))

        return chapter_models


    async def refreshLibrary(self):
        await self.shared(('library',), self.loadLibrary)

    async def loadLibrary(self):
        result = await self.query(GET_LIBRARY)
        if 'mangas' not in result:
            return  # the request failed, keep what we have
        nodes = result['mangas'].get('nodes') or []
        manga_models = [self.makeModel(node, 'Manga') for node in nodes]
        manga_models = [m for m in manga_models if m is not None]

        if list(self.library) != manga_models:
            self.library.splice(0, self.library.get_n_items(), manga_models)

    def syncLibraryMembership(self, model: models.Manga, in_library: bool):
        found, position = self.library.find(model)
        if in_library and not found:
            self.library.append(model)
        elif not in_library and found:
            self.library.remove(position)

    async def refreshExtensions(self):
        await self.shared(('extensions',), self.loadExtensions)

    async def loadExtensions(self):
        result = await self.query(FETCH_EXTENSIONS, retries=2)
        data = result.get('fetchExtensions')
        if data is None:
            return  # request failed, keep what we have
        nodes = data.get('extensions') or []
        extension_models = [self.makeModel(node, 'Extension') for node in nodes]
        extension_models = [m for m in extension_models if m is not None]
        if list(self.extensions) != extension_models:
            self.extensions.splice(0, self.extensions.get_n_items(), extension_models)

    async def refreshSources(self):
        await self.shared(('sources',), self.loadSources)

    async def loadSources(self):
        result = await self.query(GET_SOURCES)
        if 'sources' not in result:
            return
        nodes = result['sources'].get('nodes') or []
        source_models = [self.makeModel(node, 'Source') for node in nodes]
        source_models = [m for m in source_models if m is not None]
        if list(self.sources) != source_models:
            self.sources.splice(0, self.sources.get_n_items(), source_models)

    async def getSourceManga(
        self,
        source_id: str,
        fetch_type: str = SourceMangaType.POPULAR,
        page: int = 1,
        query: str | None = None,
        filters: list | None = None,
    ) -> list:
        variables = {
            "source": source_id,
            "type": fetch_type,
            "page": page,
            "query": query,
            "filters": filters or None,
        }
        result = await self.query(GET_SOURCE_MANGA, variable_values=variables, raise_errors=True)
        nodes = result.get('fetchSourceManga', {}).get('mangas', [])
        manga_models = [self.makeModel(node, 'Manga') for node in nodes]
        return [m for m in manga_models if m is not None]

    def makeFilter(self, node: dict) -> dict:
        default = None
        for key in ("checkBoxDefault", "selectDefault", "triStateDefault", "textDefault", "sortDefault"):
            if key in node:
                default = node[key]
                break
        return {
            "type": node.get("type"),
            "name": node.get("name") or "",
            "default": default,
            "values": node.get("values") or [],
            "filters": [self.makeFilter(child) for child in node.get("filters") or []],
        }

    async def getSourceFilters(self, source_id: str) -> list:
        result = await self.query(GET_SOURCE_FILTERS, variable_values={"id": source_id})
        nodes = (result.get('source') or {}).get('filters') or []
        return [self.makeFilter(node) for node in nodes]


    async def changeExtension(self, pkg_name: str, **patch):
        model = self.getModel(pkg_name, 'Extension')
        if model:
            model.is_busy = True
        try:
            result = await self.query(UPDATE_EXTENSION, variable_values={"pkgName": pkg_name, **patch})
            node = result.get('updateExtension', {}).get('extension')
            if node:
                self.makeModel(node, 'Extension')
        finally:
            if model:
                model.is_busy = False

    async def installExtension(self, pkg_name: str):
        await self.changeExtension(pkg_name, install=True)

    async def updateExtension(self, pkg_name: str):
        await self.changeExtension(pkg_name, update=True)

    async def uninstallExtension(self, pkg_name: str):
        await self.changeExtension(pkg_name, uninstall=True)


    def makePageModel(self, chapter_id: int, index: int, url: str) -> models.Page:
        return models.Page(
            index=index,
            chapter_id=chapter_id,
            url=urljoin(self.url, url),
        )

    async def getChapterPages(self, chapter_id: int) -> list:
        result = await self.query(FETCH_CHAPTER_PAGES, variable_values={"chapterId": chapter_id})
        data = result.get('fetchChapterPages', {})
        urls = data.get('pages', [])
        page_models = [self.makePageModel(chapter_id, index, url) for index, url in enumerate(urls)]

        chapter_node = data.get('chapter')
        if chapter_node:
            chapter_model = self.getModel(chapter_id, 'Chapter')
            if chapter_model:
                chapter_model.update_data(
                    page_count=chapter_node.get('pageCount', len(urls)),
                    is_downloaded=chapter_node.get('isDownloaded', False),
                )
            manga_node = chapter_node.get('manga')
            if manga_node:
                manga_model = self.getModel(manga_node.get('id'), 'Manga')
                if manga_model:
                    manga_model.set_property('download_count', manga_node.get('downloadCount', 0))

        return page_models

    async def updateChapter(
        self,
        chapter_id: int,
        is_read: bool | None = None,
        is_bookmarked: bool | None = None,
        last_page_read: int | None = None,
    ):
        variables = {"id": chapter_id}
        if is_read is not None:
            variables["isRead"] = is_read
        if is_bookmarked is not None:
            variables["isBookmarked"] = is_bookmarked
        if last_page_read is not None:
            variables["lastPageRead"] = last_page_read

        model = self.getModel(chapter_id, 'Chapter')
        if model:
            model.update_data(**{
                name: value for name, value in (
                    ("is_read", is_read),
                    ("is_bookmarked", is_bookmarked),
                    ("last_page_read", last_page_read),
                ) if value is not None
            })

        result = await self.query(UPDATE_CHAPTER, variable_values=variables)
        node = result.get('updateChapter', {}).get('chapter')
        if node is None:
            return
        manga_node = node.pop('manga', None)
        self.makeModel(node, 'Chapter')  # server truth, applied on top
        if manga_node:
            manga_model = self.getModel(manga_node.get('id'), 'Manga')
            if manga_model:
                manga_model.set_property('unread_count', manga_node.get('unreadCount', manga_model.unread_count))

    async def deleteDownloadedChapter(self, chapter_id: int):
        model = self.getModel(chapter_id, 'Chapter')
        if model:
            model.update_data(is_downloaded=False)

        result = await self.query(DELETE_DOWNLOADED_CHAPTER, variable_values={"id": chapter_id})
        chapters = result.get('deleteDownloadedChapter', {}).get('chapters') or []
        if isinstance(chapters, dict):
            chapters = [chapters]

        for node in chapters:
            manga_node = node.pop('manga', None)
            chapter_model = self.getModel(node.get('id'), 'Chapter')
            if chapter_model:
                chapter_model.set_property('is_downloaded', node.get('isDownloaded', False))
            if manga_node:
                manga_model = self.getModel(manga_node.get('id'), 'Manga')
                if manga_model:
                    manga_model.set_property('download_count', manga_node.get('downloadCount', 0))

    async def setMangaLibrary(self, manga_id: int, in_library: bool):
        model = self.getModel(manga_id, 'Manga')
        if model:
            model.update_data(in_library=in_library)
            self.syncLibraryMembership(model, in_library)

        result = await self.query(
            SET_MANGA_LIBRARY,
            variable_values={"id": manga_id, "inLibrary": in_library},
        )
        node = result.get('updateManga', {}).get('manga')
        if node is None or model is None:
            return
        model.update_data(
            in_library=node.get('inLibrary', in_library),
            in_library_at=node.get('inLibraryAt', ''),
            unread_count=node.get('unreadCount', model.unread_count),
        )
        self.syncLibraryMembership(model, model.in_library)

    async def addToLibrary(self, manga_id: int):
        await self.setMangaLibrary(manga_id, True)

    async def removeFromLibrary(self, manga_id: int):
        await self.setMangaLibrary(manga_id, False)


    def makeDownloadModel(self, item: dict) -> models.Download | None:
        chapter = item.get('chapter') or {}
        manga = item.get('manga') or {}
        chapter_id = chapter.get('id')
        if chapter_id is None:
            return None
        key = ('Download', chapter_id)
        model = self.loaded_models.get(key)
        if model is None:
            model = models.Download()
            self.loaded_models[key] = model
        model.update_data(
            chapter_id=chapter_id,
            chapter_name=chapter.get('name') or "",
            manga_id=manga.get('id') or 0,
            manga_title=manga.get('title') or "",
            progress=item.get('progress') or 0.0,
            state=item.get('state') or "",
            tries=item.get('tries') or 0,
        )
        return model

    async def getDownloadStatus(self):
        result = await self.query(GET_DOWNLOAD_STATUS)
        status = result.get('downloadStatus')
        if not status:
            return
        self.downloader_state = status.get('state') or self.downloader_state

        items = status.get('queue') or []
        new_models = [self.makeDownloadModel(item) for item in items]
        new_models = [m for m in new_models if m is not None]

        current_ids = [m.chapter_id for m in self.download_queue]
        new_ids = [m.chapter_id for m in new_models]
        if current_ids != new_ids:
            self.download_queue.splice(0, len(current_ids), new_models)

    async def downloadCommand(self, gql_query, variables=None):
        await self.query(gql_query, variable_values=variables)
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


    async def getReaderSettings(self, manga_id: int) -> dict:
        result = await self.query(GET_READER_META, variable_values={"id": manga_id})
        global_meta = (result.get('metas') or {}).get('nodes') or []
        manga_meta = (result.get('manga') or {}).get('meta') or []

        values = {m['key']: m['value'] for m in global_meta}
        values.update({m['key']: m['value'] for m in manga_meta})

        settings = {}
        mode = self.readMeta(values, self.MODE_KEY)
        if mode in READING_MODES:
            settings["mode"], settings["orientation"] = READING_MODES[mode]
        direction = self.readMeta(values, self.DIRECTION_KEY)
        if direction in (0, 1):
            settings["direction"] = "rtl" if direction == 1 else "ltr"
        return settings

    def readMeta(self, values: dict, key: str):
        try:
            return json.loads(values[key])
        except (KeyError, json.JSONDecodeError):
            return None

    async def setReaderSettings(self, manga_id: int, settings: dict):
        if settings["mode"] == "single":
            mode = 0
        elif settings["mode"] == "double":
            mode = 1
        elif settings["orientation"] == "horizontal":
            mode = 3
        else:
            mode = 4
        direction = 1 if settings["direction"] == "rtl" else 0

        await asyncio.gather(
            self.setMeta(manga_id, self.MODE_KEY, mode),
            self.setMeta(manga_id, self.DIRECTION_KEY, direction),
        )

    async def setMeta(self, manga_id: int, key: str, value):
        await self.query(SET_MANGA_META, variable_values={
            "mangaId": manga_id,
            "key": key,
            "value": json.dumps(value),
        })

    async def getGlobalReaderSettings(self) -> dict:
        result = await self.query(GET_GLOBAL_READER_META)
        nodes = (result.get('metas') or {}).get('nodes') or []
        values = {m['key']: m['value'] for m in nodes}

        settings = {}
        mode = self.readMeta(values, self.MODE_KEY)
        if mode in READING_MODES:
            settings["mode"], settings["orientation"] = READING_MODES[mode]
        direction = self.readMeta(values, self.DIRECTION_KEY)
        if direction in (0, 1):
            settings["direction"] = "rtl" if direction == 1 else "ltr"
        return settings

    async def setGlobalReadingMode(self, mode: str, orientation: str):
        value = GLOBAL_MODE_VALUES.get(mode)
        if value is None:  # webtoon
            value = 3 if orientation == "horizontal" else 4
        await self.setGlobalMeta(self.MODE_KEY, value)

    async def setGlobalReadingDirection(self, direction: str):
        await self.setGlobalMeta(self.DIRECTION_KEY, 1 if direction == "rtl" else 0)

    async def setGlobalMeta(self, key: str, value):
        await self.query(SET_GLOBAL_META, variable_values={
            "key": key,
            "value": json.dumps(value),
        })

    async def getServerSettings(self) -> dict:
        result = await self.query(GET_SERVER_SETTINGS)
        return result.get('settings') or {}

    async def setServerSettings(self, **settings):
        await self.query(SET_SERVER_SETTINGS, variable_values={"settings": settings})

    async def setDownloadAsCbz(self, value: bool):
        await self.setServerSettings(downloadAsCbz=value)

    async def setDownloadsPath(self, path: str):
        await self.setServerSettings(downloadsPath=path)

    async def getExtensionStores(self) -> list:
        settings = await self.getServerSettings()
        return settings.get('extensionRepos') or []

    async def setExtensionStores(self, urls: list):
        await self.setServerSettings(extensionRepos=urls)
