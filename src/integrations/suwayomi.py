import gi
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, GObject

import asyncio
import base64
import enum
import json
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from gettext import gettext as _
from pathlib import Path
from urllib.parse import urljoin

import httpx
from babel import Locale
from diskcache import Cache
from gql import Client, FileVar
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError, TransportServerError

from . import models
from .live import LiveUpdates
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
EXTENSION_POLL_TICKS = 180
AUTO_UPDATE_INTERVAL = 30 * 60
AUTO_UPDATE_RETRY = 60
UPDATE_POLL_INTERVAL = 3
LOCAL_SOURCE_ID = "0"
DEFAULT_CATEGORY_ID = 0
THUMB_CACHE_ITEMS = 256
FEED_PAGE_SIZE = 50
CHECK_TIMEOUT = 10
RESTORE_POLL_INTERVAL = 1
LOGIN_MODES = ("UI_LOGIN", "SIMPLE_LOGIN")
DOWNLOAD_LIST_CHANGES = {"QUEUED", "DEQUEUED", "FINISHED", "POSITION", "ERROR"}

READING_MODES = {
    0: ("single", "vertical"),
    1: ("double", "vertical"),
    2: ("webtoon", "vertical"),
    3: ("webtoon", "horizontal"),
    4: ("webtoon", "vertical"),
}
CHAPTER_VARS = {name: key for key, name in CHAPTER_FIELDS.items()}
FILTER_DEFAULTS = ("checkBoxDefault", "selectDefault", "triStateDefault", "textDefault", "sortDefault")


class ConnectionFailed(Exception):
    pass


class ServerUnreachable(ConnectionFailed):
    pass


class LoginFailed(ConnectionFailed):
    pass


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


def directionValue(direction: str) -> int:
    return 1 if direction == "rtl" else 0


def mapped(item: dict, fields: dict) -> dict:
    return {name: item[key] for key, name in fields.items() if key in item}


def graphqlUrl(url: str) -> str:
    return url.rstrip('/') + '/api/graphql'


def makeClient(url: str) -> Client:
    transport = AIOHTTPTransport(timeout=GRAPHQL_TIMEOUT, url=graphqlUrl(url))
    return Client(transport=transport, fetch_schema_from_transport=False)


def isUnauthorized(error: Exception) -> bool:
    if isinstance(error, TransportServerError):
        return error.code == 401
    return isinstance(error, TransportQueryError) and "Unauthorized" in str(error)


def readPreference(position: int, node: dict) -> dict:
    value = None
    for key in ("switchValue", "checkValue", "textValue", "listValue", "multiValue"):
        if key in node:
            value = node[key]
    return {
        "position": position,
        "type": node["type"],
        "key": node.get("key") or "",
        "title": node.get("title") or "",
        "summary": node.get("summary") or "",
        "visible": node.get("visible", True),
        "enabled": node.get("enabled", True),
        "value": value,
        "entries": node.get("entries") or [],
        "entry_values": node.get("entryValues") or [],
        "dialog_message": node.get("dialogMessage") or "",
    }


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
    history_revision = GObject.Property(type=int, default=0)
    updates_revision = GObject.Property(type=int, default=0)
    library_revision = GObject.Property(type=int, default=0)
    selected_category = GObject.Property(type=int, default=-1)
    updating = GObject.Property(type=bool, default=False)
    update_progress = GObject.Property(type=float, default=0.0)
    live = GObject.Property(type=bool, default=False)
    extension_updates = GObject.Property(type=int, default=0)
    new_updates = GObject.Property(type=int, default=0)

    def __init__(self):
        super().__init__()
        self.loaded_models = {}
        self.pending = {}
        self.chapter_writes = {}
        self.prefetched = set()
        self.background = set()
        self.session = None
        self.poller = None
        self.updater = None
        self.update_stamp = None
        self.connect_lock = asyncio.Lock()
        self.login_lock = asyncio.Lock()
        self.username = ""
        self.password = ""
        self.auth_mode = "NONE"
        self.access_token = ""
        self.session_cookie = ""
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
        self.thumbnail_users = {}
        self.category_members = {}

        self.download_queue = Gio.ListStore(item_type=models.Download)
        self.library = Gio.ListStore(item_type=models.Manga)
        self.categories = Gio.ListStore(item_type=models.Category)
        self.sources = Gio.ListStore(item_type=models.Source)
        self.all_sources = Gio.ListStore(item_type=models.Source)
        self.extensions = Gio.ListStore(item_type=models.Extension)

        self.languages = ["en", "all"]
        self.updates_seen_at = ""
        self.live_updates = LiveUpdates(self)
        self.connect("notify::updates-revision", lambda *args: self.runInBackground(self.countNewUpdates()))

    def runInBackground(self, job):
        task = asyncio.create_task(job)
        self.background.add(task)
        task.add_done_callback(self.finishBackgroundTask)

    def finishBackgroundTask(self, task):
        self.background.discard(task)
        if not task.cancelled() and task.exception():
            print(f"background job failed: {task.exception()}")

    def websocketUrl(self) -> str:
        address = graphqlUrl(self.url)
        if address.startswith("https://"):
            return "wss://" + address[len("https://"):]
        return "ws://" + address[len("http://"):]

    def forgetServerData(self):
        self.loaded_models.clear()
        self.prefetched.clear()
        self.thumbs.clear()
        self.category_members = {}
        self.selected_category = -1
        self.updating = False
        self.extension_updates = 0
        self.new_updates = 0
        for store in (self.download_queue, self.library, self.categories,
                      self.sources, self.all_sources, self.extensions):
            store.remove_all()

    async def reconnect(self, url: str, username: str = "", password: str = ""):
        self.stopPolling()
        if url != self.url:
            self.forgetServerData()
        old_client = self.client
        was_connected = self.session is not None
        self.session = None
        self.update_stamp = None
        self.url = url
        self.username = username
        self.password = password
        self.auth_mode = "NONE"
        self.access_token = ""
        self.session_cookie = ""
        self.client = makeClient(url)
        if was_connected:
            await old_client.close_async()

    async def disconnect(self):
        await self.reconnect(self.url, self.username, self.password)

    def setLogin(self, username: str, password: str):
        self.username = username
        self.password = password

    def authHeaders(self) -> dict:
        if self.auth_mode == "BASIC_AUTH":
            login = f"{self.username}:{self.password}".encode()
            return {"Authorization": "Basic " + base64.b64encode(login).decode()}
        if self.auth_mode == "UI_LOGIN":
            return {"Authorization": f"Bearer {self.access_token}"}
        if self.auth_mode == "SIMPLE_LOGIN":
            return {"Cookie": f"JSESSIONID={self.session_cookie}"}
        return {}

    def headersFor(self, url: str) -> dict:
        if url.startswith(self.url):
            return self.authHeaders()
        return {}

    async def probe(self) -> str:
        self.http.cookies.clear()
        try:
            response = await self.http.post(
                graphqlUrl(self.url),
                json={"query": PROBE_TEXT},
                headers=self.authHeaders(),
                timeout=CHECK_TIMEOUT,
                follow_redirects=False,
            )
        except httpx.HTTPError as error:
            raise ServerUnreachable(_("Couldn't reach the server. Check the address and that the server is running.")) from error

        if response.status_code == 401:
            return "needs-basic-login"
        try:
            result = response.json()
        except ValueError:
            result = None
        if not isinstance(result, dict) or not ("data" in result or "errors" in result):
            raise ServerUnreachable(_("This address doesn't look like a Suwayomi server."))

        for error in result.get("errors") or []:
            if "Unauthorized" in error.get("message", ""):
                return "needs-login"
        return "ok"

    async def checkConnection(self):
        self.auth_mode = "NONE"
        answer = await self.probe()
        if answer == "ok":
            return

        if not self.username:
            raise LoginFailed(_("This server needs a username and password."))

        if answer == "needs-basic-login":
            self.auth_mode = "BASIC_AUTH"
        else:
            await self.findLoginMode()

        if await self.probe() != "ok":
            raise LoginFailed(_("The username or password is wrong."))

    async def findLoginMode(self):
        self.auth_mode = "UI_LOGIN"
        await self.logIn()
        if await self.probe() == "ok":
            return
        self.auth_mode = "SIMPLE_LOGIN"
        await self.logIn()

    async def logIn(self):
        async with self.login_lock:
            try:
                if self.auth_mode == "UI_LOGIN":
                    await self.logInWithToken()
                elif self.auth_mode == "SIMPLE_LOGIN":
                    await self.logInWithCookie()
            except httpx.HTTPError as error:
                raise ServerUnreachable(_("Couldn't reach the server. Check the address and that the server is running.")) from error

    async def logInWithToken(self):
        response = await self.http.post(
            graphqlUrl(self.url),
            json={"query": LOGIN_TEXT, "variables": {"username": self.username, "password": self.password}},
            timeout=CHECK_TIMEOUT,
        )
        data = response.json().get("data") or {}
        self.access_token = (data.get("login") or {}).get("accessToken", "")
        if not self.access_token:
            raise LoginFailed(_("The username or password is wrong."))

    async def logInWithCookie(self):
        self.http.cookies.clear()
        response = await self.http.post(
            self.url.rstrip('/') + '/login.html',
            data={"user": self.username, "pass": self.password},
            timeout=CHECK_TIMEOUT,
            follow_redirects=False,
        )
        self.session_cookie = response.cookies.get("JSESSIONID") or ""
        if response.status_code != 303 or not self.session_cookie:
            raise LoginFailed(_("The username or password is wrong."))

    async def close(self):
        self.stopPolling()
        for task in list(self.background):
            task.cancel()
        if self.session is not None:
            await self.client.close_async()
        await self.http.aclose()
        self.decoder.shutdown()
        self.cache.close()

    def startPoller(self):
        if self.poller is None:
            self.poller = asyncio.create_task(self.poll())

    def startPolling(self):
        self.startPoller()
        if self.updater is None:
            self.updater = asyncio.create_task(self.autoUpdate())

    def stopPolling(self):
        self.live_updates.stop()
        for name in ("poller", "updater"):
            task = getattr(self, name)
            if task:
                task.cancel()
                setattr(self, name, None)

    async def poll(self):
        ticks = 0
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            ticks += 1
            jobs = [self.checkUpdates()]
            if not self.live:
                jobs.append(self.getDownloadStatus())
            if ticks % LIBRARY_POLL_TICKS == 0:
                jobs.append(self.refreshLibrary())
            if ticks % SOURCE_POLL_TICKS == 0:
                jobs.append(self.refreshSources())
            if ticks % EXTENSION_POLL_TICKS == 0:
                jobs.append(self.refreshExtensions())
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

    async def checkUpdates(self):
        stamp = await self.getLastUpdateTimestamp()
        if self.update_stamp is None:
            self.update_stamp = stamp
        elif stamp != self.update_stamp:
            self.update_stamp = stamp
            self.updates_revision += 1

    async def getSession(self):
        async with self.connect_lock:
            if self.session is None:
                self.session = await self.client.connect_async()
                self.startPoller()
                self.live_updates.start()
        return self.session

    async def query(self, gql_query, variable_values=None, upload_files=False) -> dict:
        session = await self.getSession()
        try:
            return await self.send(session, gql_query, variable_values, upload_files)
        except (TransportQueryError, TransportServerError) as error:
            if upload_files or self.auth_mode not in LOGIN_MODES or not isUnauthorized(error):
                raise
        await self.logIn()
        return await self.send(session, gql_query, variable_values, upload_files)

    async def send(self, session, gql_query, variable_values, upload_files) -> dict:
        return await session.execute(
            gql_query,
            variable_values=variable_values,
            upload_files=upload_files,
            extra_args={"headers": self.authHeaders()},
        )

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
            response = await self.http.get(url, headers=self.headersFor(url))
            if response.status_code == 401 and self.auth_mode in LOGIN_MODES:
                await self.logIn()
                response = await self.http.get(url, headers=self.headersFor(url))
            response.raise_for_status()
            data = response.content
            await asyncio.to_thread(self.cache.set, url, data, expire=IMAGE_TTL)
        return data

    def sharedBytes(self, url: str):
        return self.shared(('bytes', url), lambda: self.loadBytes(url))

    @staticmethod
    def decode(raw: bytes) -> Gdk.Paintable:
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(raw))

    async def getPaintable(self, url: str) -> Gdk.Paintable:
        raw = await self.sharedBytes(url)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.decoder, self.decode, raw)

    async def loadIcon(self, item):
        if not item.icon_url:
            return
        try:
            item.paintable = await self.getPaintable(item.icon_url)
        except Exception as error:
            print(f"icon failed: {item.icon_url}: {error}")

    async def loadPage(self, page: models.Page):
        try:
            paintable = await self.getPaintable(page.url)
        except Exception as error:
            print(f"page failed: {page.url}: {error}")
            return
        ratio = paintable.get_intrinsic_aspect_ratio()
        page.update_data(paintable=paintable, ratio=ratio if ratio > 0 else page.ratio)

    def prefetch(self, url: str):
        if not url or url in self.prefetched:
            return
        self.prefetched.add(url)
        task = asyncio.create_task(self.prefetchBytes(url))
        self.background.add(task)
        task.add_done_callback(self.background.discard)

    async def prefetchBytes(self, url: str):
        try:
            await self.sharedBytes(url)
        except Exception:
            self.prefetched.discard(url)

    def cachedThumbnail(self, url: str):
        texture = self.thumbs.get(url)
        if texture is not None:
            self.thumbs.move_to_end(url)
        return texture

    async def getThumbnail(self, url: str) -> Gdk.Paintable:
        texture = self.cachedThumbnail(url)
        if texture is not None:
            return texture
        texture = await self.getPaintable(url)
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
        self.thumbnail_users[item] = self.thumbnail_users.get(item, 0) + 1
        if item.paintable is not None or not item.thumbnail_url:
            return None
        cached = self.cachedThumbnail(item.thumbnail_url)
        if cached is not None:
            item.paintable = cached
            return None
        return asyncio.create_task(self.loadThumbnail(item))

    def stopThumbnail(self, item, task):
        if task:
            task.cancel()
        count = self.thumbnail_users.get(item, 0) - 1
        if count > 0:
            self.thumbnail_users[item] = count
            return
        self.thumbnail_users.pop(item, None)
        item.paintable = None

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

    def absoluteUrl(self, path: str | None) -> str:
        if path:
            return urljoin(self.url, path)
        return ""

    def fillManga(self, model, item: dict):
        values = mapped(item, MANGA_FIELDS)
        values.update(mapped(item, MANGA_LIBRARY_FIELDS))
        for key, name in MANGA_CHAPTER_LINKS.items():
            if key in item:
                values[name] = self.makeModel(item[key], 'Chapter')
        if 'thumbnailUrl' in item:
            values['thumbnail_url'] = self.absoluteUrl(item['thumbnailUrl'])
        model.update_data(id=item['id'], **values)

        chapters = item.get('chapters')
        if chapters:
            if 'totalCount' in chapters:
                model.total_chapters = chapters['totalCount']
            if 'nodes' in chapters:
                chapter_models = self.makeModels(chapters['nodes'], 'Chapter')
                self.replace(model.chapters, chapter_models)

    def fillChapter(self, model, item: dict):
        model.update_data(id=item['id'], **mapped(item, CHAPTER_FIELDS))

    def fillCategory(self, model, item: dict):
        model.update_data(
            id=item['id'],
            name=item['name'],
            order=item.get('order', 0),
            is_default=item.get('default', False),
            manga_count=item.get('mangaCount', 0),
        )

    def fillExtension(self, model, item: dict):
        values = mapped(item, EXTENSION_FIELDS)
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
        model = await self.getManga(manga_id, force=True)
        self.updates_revision += 1
        return model

    async def fetchManga(self, manga_id: int) -> models.Manga:
        variables = {"id": manga_id, "fetchManga": True, "fetchChapters": True}
        result = await self.query(FETCH_MANGA, variables)
        data = result['fetchMangaAndChapters']
        chapters = data['chapters']
        node = dict(data['manga'])
        node['chapters'] = {'nodes': chapters, 'totalCount': len(chapters)}
        return self.makeModel(node, 'Manga')

    async def getChapters(self, manga_id: int) -> list:
        result = await self.query(GET_CHAPTERS_MANGA, {"mangaId": manga_id})
        connection = result['chapters']
        chapter_models = self.makeModels(connection['nodes'], 'Chapter')
        model = self.getModel(manga_id, 'Manga')
        if model:
            self.replace(model.chapters, chapter_models)
            model.total_chapters = connection['totalCount']
        return chapter_models

    async def fetchChapterFeed(self, gql_query, offset: int) -> tuple[list, bool]:
        result = await self.query(gql_query, {"first": FEED_PAGE_SIZE, "offset": offset})
        connection = result['chapters']
        chapters = []
        for node in connection['nodes']:
            chapter = self.makeModel(node, 'Chapter')
            chapter.manga = self.makeModel(node['manga'], 'Manga')
            chapters.append(chapter)
        return chapters, connection['pageInfo']['hasNextPage']

    async def getHistory(self, offset: int = 0) -> tuple[list, bool]:
        return await self.fetchChapterFeed(GET_RECENTLY_READ_CHAPTERS, offset)

    async def getUpdates(self, offset: int = 0) -> tuple[list, bool]:
        return await self.fetchChapterFeed(GET_RECENTLY_UPDATED_CHAPTERS, offset)

    async def getLastUpdateTimestamp(self) -> str:
        result = await self.query(GET_LAST_UPDATE_TIMESTAMP)
        return result['lastUpdateTimestamp']['timestamp']

    async def refreshLibrary(self):
        await self.shared('library', self.loadLibrary)

    async def loadLibrary(self):
        library_result, category_result = await asyncio.gather(
            self.query(GET_LIBRARY),
            self.query(GET_CATEGORIES),
        )

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
        self.library_revision += 1

    def buildCategories(self, nodes: list, manga_models: list):
        members = {}
        category_models = []
        assigned = set()

        for node in sorted(nodes, key=lambda node: node['order']):
            if node['id'] == DEFAULT_CATEGORY_ID:
                continue
            ids = set(manga['id'] for manga in node['mangas']['nodes'])
            assigned |= ids
            members[node['id']] = ids
            node_data = dict(node)
            node_data['mangaCount'] = len(ids)
            category_models.append(self.makeModel(node_data, 'Category'))

        default_ids = set(manga.id for manga in manga_models) - assigned
        if default_ids:
            members[DEFAULT_CATEGORY_ID] = default_ids
            default_data = {
                'id': DEFAULT_CATEGORY_ID,
                'name': _('Default'),
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

    async def updateLibrary(self, categories: list | None = None):
        if self.updating:
            return
        self.updating = True
        try:
            await self.query(UPDATE_LIBRARY, {"categories": categories})
            while True:
                await asyncio.sleep(UPDATE_POLL_INTERVAL)
                result = await self.query(GET_LIBRARY_UPDATE_STATUS)
                if not result['libraryUpdateStatus']['jobsInfo']['isRunning']:
                    break
        finally:
            self.updating = False
        await self.refreshLibrary()
        self.updates_revision += 1

    async def stopLibraryUpdate(self):
        await self.query(STOP_LIBRARY_UPDATE)

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
        self.countExtensionUpdates()

    def countExtensionUpdates(self):
        self.extension_updates = sum(1 for extension in self.extensions if extension.has_update)

    async def refreshSources(self):
        await self.shared('sources', self.loadSources)

    async def loadSources(self):
        results = await asyncio.gather(self.query(GET_SOURCES), self.getBrowseLanguages())
        source_models = self.makeModels(results[0]['sources']['nodes'], 'Source')
        self.replace(self.all_sources, source_models)
        self.applyLanguages()

    def applyLanguages(self):
        visible_sources = [
            source for source in self.all_sources
            if source.lang in self.languages or source.id == LOCAL_SOURCE_ID
        ]
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

        return {
            "type": node.get("type"),
            "name": node.get("name") or "",
            "default": default,
            "values": node.get("values") or [],
            "filters": [self.makeFilter(child) for child in node.get("filters") or []],
        }

    async def getSourceFilters(self, source_id: str) -> list:
        result = await self.query(GET_SOURCE_FILTERS, {"id": source_id})
        return [self.makeFilter(node) for node in result['source']['filters']]

    async def changeExtension(self, pkg_name: str, **patch):
        model = self.getModel(pkg_name, 'Extension')
        model.is_busy = True
        try:
            result = await self.query(UPDATE_EXTENSION, {"pkgName": pkg_name, **patch})
            self.makeModel(result['updateExtension']['extension'], 'Extension')
            self.countExtensionUpdates()
            await self.refreshSources()
        finally:
            model.is_busy = False

    async def installExtension(self, pkg_name: str):
        await self.changeExtension(pkg_name, install=True)

    async def updateExtension(self, pkg_name: str):
        await self.changeExtension(pkg_name, update=True)

    async def uninstallExtension(self, pkg_name: str):
        await self.changeExtension(pkg_name, uninstall=True)

    def makePageModel(self, chapter_id: int, index: int, url: str) -> models.Page:
        return models.Page(index=index, chapter_id=chapter_id, url=self.absoluteUrl(url))

    async def fetchChapterPages(self, chapter_id: int) -> list:
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
        return data['pages']

    async def getChapterPages(self, chapter_id: int) -> list:
        urls = await self.shared(('pages', chapter_id), lambda: self.fetchChapterPages(chapter_id))
        return [self.makePageModel(chapter_id, index, url) for index, url in enumerate(urls)]

    async def updateChapter(self, chapter_id: int, **changes):
        chapter = self.getModel(chapter_id, 'Chapter')
        previous = {name: getattr(chapter, name) for name in changes}
        chapter.update_data(**changes)

        variables = {"id": chapter_id}
        for name, value in changes.items():
            variables[CHAPTER_VARS[name]] = value

        self.chapter_writes[chapter_id] = self.chapter_writes.get(chapter_id, 0) + 1
        try:
            result = await self.query(UPDATE_CHAPTER, variables)
        except Exception:
            if self.chapter_writes[chapter_id] == 1:
                chapter.update_data(**previous)
            raise
        finally:
            self.chapter_writes[chapter_id] -= 1

        node = result['updateChapter']['chapter']
        if self.chapter_writes[chapter_id] == 0:
            self.makeModel(node, 'Chapter')
        manga_model = self.getModel(node['manga']['id'], 'Manga')
        manga_model.unread_count = node['manga']['unreadCount']

        if "is_read" in changes:
            self.library_revision += 1

        if "is_read" in changes or "last_page_read" in changes:
            self.history_revision += 1

    async def deleteDownloadedChapter(self, chapter_id: int):
        chapter = self.getModel(chapter_id, 'Chapter')
        was_downloaded = chapter.is_downloaded
        chapter.is_downloaded = False

        try:
            result = await self.query(DELETE_DOWNLOADED_CHAPTER, {"id": chapter_id})
        except Exception:
            chapter.is_downloaded = was_downloaded
            raise

        node = result['deleteDownloadedChapter']['chapters']
        self.makeModel(node, 'Chapter')
        manga_model = self.getModel(node['manga']['id'], 'Manga')
        manga_model.download_count = node['manga']['downloadCount']

    async def setMangaLibrary(self, manga_id: int, in_library: bool):
        model = self.getModel(manga_id, 'Manga')
        was_in_library = model.in_library
        model.in_library = in_library
        self.syncLibraryMembership(model, in_library)

        try:
            result = await self.query(SET_MANGA_LIBRARY, {"id": manga_id, "inLibrary": in_library})
        except Exception:
            model.in_library = was_in_library
            self.syncLibraryMembership(model, was_in_library)
            raise

        node = result['updateManga']['manga']
        model.update_data(in_library_at=node['inLibraryAt'], unread_count=node['unreadCount'])

        if in_library:
            await self.addToDefaultCategory(manga_id)
            await self.refreshLibrary()

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
        await self.shared('downloads', self.loadDownloadStatus)

    async def loadDownloadStatus(self):
        result = await self.query(GET_DOWNLOAD_STATUS)
        status = result['downloadStatus']
        self.downloader_state = status['state']

        new_queue = [self.makeDownloadModel(item) for item in status['queue']]

        queued = set(new_queue)
        finished_manga_ids = {
            download.manga_id for download in self.download_queue if download not in queued
        }

        self.replace(self.download_queue, new_queue)

        await asyncio.gather(*[self.getChapters(manga_id) for manga_id in finished_manga_ids])

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
        return {meta['key']: meta['value'] for meta in nodes}

    def readMeta(self, values: dict, key: str):
        value = values.get(key)
        if value:
            return json.loads(value)
        return None

    def parseReaderSettings(self, values: dict) -> dict:
        settings = {}

        mode = self.readMeta(values, self.MODE_KEY)
        if mode is not None:
            settings["mode"], settings["orientation"] = READING_MODES[mode]

        direction = self.readMeta(values, self.DIRECTION_KEY)
        if direction is not None:
            settings["direction"] = "rtl" if direction == 1 else "ltr"

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
        await asyncio.gather(
            self.setMeta(manga_id, self.MODE_KEY, readingModeValue(settings["mode"], settings["orientation"])),
            self.setMeta(manga_id, self.DIRECTION_KEY, directionValue(settings["direction"])),
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
        await self.setGlobalMeta(self.DIRECTION_KEY, directionValue(direction))

    async def setGlobalMeta(self, key: str, value):
        await self.query(SET_GLOBAL_META, {"key": key, "value": json.dumps(value)})

    async def getServerSettings(self) -> dict:
        result = await self.query(GET_SERVER_SETTINGS)
        return result['settings']

    async def setServerSettings(self, **settings):
        await self.query(SET_SERVER_SETTINGS, {"settings": settings})

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
            return _("All languages")
        if not lang or lang == "localsourcelang":
            return _("Other")
        try:
            return Locale.parse(lang, sep="-").get_display_name("en")
        except Exception:
            return lang.upper()

    def mangaCategoryIds(self, manga_id: int) -> set:
        return {
            category_id for category_id, members in self.category_members.items()
            if category_id != DEFAULT_CATEGORY_ID and manga_id in members
        }

    async def libraryCommand(self, gql_query, variables):
        await self.query(gql_query, variables)
        await self.refreshLibrary()

    async def setMangaCategories(self, manga_id: int, add: list, remove: list):
        await self.libraryCommand(SET_MANGA_CATEGORIES, {"id": manga_id, "add": add, "remove": remove})

    async def createCategory(self, name: str):
        await self.libraryCommand(CREATE_CATEGORY, {"name": name})

    async def renameCategory(self, category_id: int, name: str):
        await self.query(UPDATE_CATEGORY, {"id": category_id, "name": name})
        self.getModel(category_id, 'Category').update_data(name=name)

    async def deleteCategory(self, category_id: int):
        await self.libraryCommand(DELETE_CATEGORY, {"id": category_id})

    async def moveCategory(self, category_id: int, position: int):
        await self.libraryCommand(REORDER_CATEGORY, {"id": category_id, "position": position})

    async def setCategoryDefault(self, category_id: int, is_default: bool):
        await self.libraryCommand(SET_CATEGORY_DEFAULT, {"id": category_id, "default": is_default})

    async def addToDefaultCategory(self, manga_id: int):
        for category in self.categories:
            if category.is_default and category.id != DEFAULT_CATEGORY_ID:
                await self.query(SET_MANGA_CATEGORIES, {"id": manga_id, "add": [category.id], "remove": []})
                return

    async def updateChapters(self, chapter_ids: list, **changes):
        if not chapter_ids:
            return
        variables = {"ids": chapter_ids}
        for name, value in changes.items():
            variables[CHAPTER_VARS[name]] = value

        result = await self.query(UPDATE_CHAPTERS, variables)
        for node in result['updateChapters']['chapters']:
            self.makeModel(node, 'Chapter')
            manga_model = self.getModel(node['manga']['id'], 'Manga')
            if manga_model:
                manga_model.unread_count = node['manga']['unreadCount']

        self.library_revision += 1
        self.history_revision += 1

    async def enqueueChapterDownloads(self, chapter_ids: list):
        if chapter_ids:
            await self.downloadCommand(ENQUEUE_CHAPTER_DOWNLOADS, {"ids": chapter_ids})

    async def updateAllExtensions(self) -> int:
        names = [extension.pkg_name for extension in self.extensions if extension.has_update]
        if not names:
            return 0
        for name in names:
            self.getModel(name, 'Extension').is_busy = True
        try:
            result = await self.query(UPDATE_EXTENSIONS, {"ids": names})
            self.makeModels(result['updateExtensions']['extensions'], 'Extension')
            self.countExtensionUpdates()
            await self.refreshSources()
        finally:
            for name in names:
                self.getModel(name, 'Extension').is_busy = False
        return len(names)

    async def installExtensionFile(self, path: str):
        with open(path, "rb") as file:
            upload = FileVar(file, filename=os.path.basename(path), content_type="application/vnd.android.package-archive")
            await self.query(INSTALL_EXTERNAL_EXTENSION, {"file": upload}, upload_files=True)
        await self.loadExtensions()
        await self.refreshSources()

    async def getSourcePreferences(self, source_id: str) -> list:
        result = await self.query(GET_SOURCE_PREFERENCES, {"id": source_id})
        nodes = result['source']['preferences']
        return [readPreference(position, node) for position, node in enumerate(nodes)]

    async def setSourcePreference(self, source_id: str, preference: dict, value) -> list:
        change = {"position": preference["position"]}
        if preference["type"] == "SwitchPreference":
            change["switchState"] = value
        elif preference["type"] == "CheckBoxPreference":
            change["checkBoxState"] = value
        elif preference["type"] == "EditTextPreference":
            change["editTextState"] = value
        elif preference["type"] == "ListPreference":
            change["listState"] = value
        elif preference["type"] == "MultiSelectListPreference":
            change["multiSelectState"] = value

        result = await self.query(SET_SOURCE_PREFERENCE, {"source": source_id, "change": change})
        nodes = result['updateSourcePreference']['preferences']
        return [readPreference(position, node) for position, node in enumerate(nodes)]

    async def downloadFile(self, url: str) -> bytes:
        address = self.absoluteUrl(url)
        response = await self.http.get(address, headers=self.headersFor(address), timeout=None)
        response.raise_for_status()
        return response.content

    async def createBackup(self, flags: dict) -> bytes:
        result = await self.query(CREATE_BACKUP, {"flags": flags})
        return await self.downloadFile(result['createBackup']['url'])

    async def validateBackup(self, path: str) -> dict:
        with open(path, "rb") as file:
            upload = FileVar(file, filename=os.path.basename(path))
            result = await self.query(VALIDATE_BACKUP, {"backup": upload}, upload_files=True)
        return result['validateBackup']

    async def restoreBackup(self, path: str, on_progress=None) -> dict:
        with open(path, "rb") as file:
            upload = FileVar(file, filename=os.path.basename(path))
            result = await self.query(RESTORE_BACKUP, {"backup": upload}, upload_files=True)

        restore_id = result['restoreBackup']['id']
        status = result['restoreBackup']['status']
        while status is None or status['state'] not in ("SUCCESS", "FAILURE"):
            await asyncio.sleep(RESTORE_POLL_INTERVAL)
            answer = await self.query(GET_RESTORE_STATUS, {"id": restore_id})
            status = answer['restoreStatus']
            if status and on_progress:
                on_progress(status)

        await asyncio.gather(self.refreshLibrary(), self.refreshSources(), return_exceptions=True)
        self.updates_revision += 1
        self.history_revision += 1
        return status

    async def getAboutServer(self) -> dict:
        result = await self.query(GET_ABOUT_SERVER)
        return result['aboutServer']

    async def clearServerImageCache(self):
        await self.query(CLEAR_CACHED_IMAGES)
        await asyncio.to_thread(self.cache.clear)
        self.thumbs.clear()

    async def clearCookiesAndCache(self):
        await self.query(CLEAR_COOKIES_AND_CACHE)

    async def getTrackers(self) -> list:
        result = await self.query(GET_TRACKERS)
        return result['trackers']['nodes']

    def trackerIconUrl(self, tracker: dict) -> str:
        return self.absoluteUrl(tracker.get('icon'))

    async def loginTrackerOAuth(self, tracker_id: int, callback_url: str) -> bool:
        result = await self.query(LOGIN_TRACKER_OAUTH, {"trackerId": tracker_id, "callbackUrl": callback_url})
        return result['loginTrackerOAuth']['isLoggedIn']

    async def loginTrackerCredentials(self, tracker_id: int, username: str, password: str) -> bool:
        variables = {"trackerId": tracker_id, "username": username, "password": password}
        result = await self.query(LOGIN_TRACKER_CREDENTIALS, variables)
        return result['loginTrackerCredentials']['isLoggedIn']

    async def logoutTracker(self, tracker_id: int):
        await self.query(LOGOUT_TRACKER, {"trackerId": tracker_id})

    async def getMangaTracking(self, manga_id: int) -> tuple[list, list]:
        result = await self.query(GET_MANGA_TRACKING, {"id": manga_id})
        return result['manga']['trackRecords']['nodes'], result['trackers']['nodes']

    async def searchTracker(self, tracker_id: int, text: str) -> list:
        result = await self.query(SEARCH_TRACKER, {"trackerId": tracker_id, "query": text})
        return result['searchTracker']['trackSearches']

    async def bindTrack(self, manga_id: int, tracker_id: int, remote_id: str, private: bool = False) -> dict:
        variables = {"mangaId": manga_id, "trackerId": tracker_id, "remoteId": remote_id, "private": private}
        result = await self.query(BIND_TRACK, variables)
        return result['bindTrack']['trackRecord']

    async def updateTrack(self, record_id: int, **changes) -> dict:
        variables = {"recordId": record_id}
        if "status" in changes:
            variables["status"] = changes["status"]
        if "score" in changes:
            variables["scoreString"] = changes["score"]
        if "last_chapter_read" in changes:
            variables["lastChapterRead"] = changes["last_chapter_read"]
        if "private" in changes:
            variables["private"] = changes["private"]
        result = await self.query(UPDATE_TRACK, variables)
        return result['updateTrack']['trackRecord']

    async def unbindTrack(self, record_id: int, delete_remote: bool = False):
        await self.query(UNBIND_TRACK, {"recordId": record_id, "deleteRemoteTrack": delete_remote})

    async def getKoSyncStatus(self) -> dict:
        result = await self.query(GET_KOSYNC_STATUS)
        return result['koSyncStatus']

    async def connectKoSync(self, server_address: str, username: str, password: str) -> dict:
        variables = {"serverAddress": server_address, "username": username, "password": password}
        result = await self.query(CONNECT_KOSYNC, variables)
        return result['connectKoSyncAccount']

    async def logoutKoSync(self):
        await self.query(LOGOUT_KOSYNC)

    async def startSync(self) -> str:
        result = await self.query(START_SYNC)
        return result['startSync']['result']

    def applyDownloadChanges(self, changes: dict):
        self.downloader_state = changes['state']
        kinds = {update['type'] for update in changes['updates']}
        if changes['initial'] is not None or changes['omittedUpdates'] or kinds & DOWNLOAD_LIST_CHANGES:
            self.runInBackground(self.getDownloadStatus())
            return
        for update in changes['updates']:
            download = update['download']
            model = self.getModel(download['chapter']['id'], 'Download')
            if model:
                model.update_data(progress=download['progress'], state=download['state'], tries=download['tries'])

    def applyLibraryUpdateChanges(self, changes: dict):
        jobs = changes['jobsInfo']
        was_updating = self.updating
        self.updating = jobs['isRunning']
        if jobs['totalJobs']:
            self.update_progress = jobs['finishedJobs'] / jobs['totalJobs']
        else:
            self.update_progress = 0.0

        finished = [update for update in changes['mangaUpdates'] if update['status'] == 'COMPLETE']
        if finished:
            self.updates_revision += 1
        if was_updating and not self.updating:
            self.runInBackground(self.refreshLibrary())

    async def newestFetch(self) -> str:
        result = await self.query(GET_NEWEST_FETCH)
        nodes = result['chapters']['nodes']
        return str(nodes[0]['fetchedAt']) if nodes else "0"

    async def countNewUpdates(self):
        if self.session is None:
            return
        try:
            if not self.updates_seen_at:
                self.updates_seen_at = await self.newestFetch()
            result = await self.query(COUNT_NEW_UPDATES, {"since": self.updates_seen_at})
            self.new_updates = result['chapters']['totalCount']
        except Exception as error:
            print(f"counting new updates failed: {error}")

    async def markUpdatesSeen(self) -> str:
        self.updates_seen_at = await self.newestFetch()
        self.new_updates = 0
        return self.updates_seen_at
