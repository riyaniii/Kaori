import asyncio
import random
from gi.repository import Adw, Gio, GObject, Gtk

from ..manga import MangaOverview
from ..containers import MangaRow

from ...integrations.suwayomi import LOCAL_SOURCE_ID, watch

MAX_ROWS = 5
ROW_SIZE = 8
CANDIDATES = 15
MAX_CONCURRENT = 3
CAROUSEL_SIZE = 6


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/home/page.ui')
class HomePage(Adw.NavigationPage):
    __gtype_name__ = "KaoriHomePage"

    manga_carousel = Gtk.Template.Child()
    carousel_stack = Gtk.Template.Child()
    main_box = Gtk.Template.Child()

    state = GObject.Property(type=str, default="home")

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.rows = []
        self.rows_task = None

        watch(self, self.suwayomi.library, self.on_library_changed)
        watch(self, self.suwayomi.sources, self.reload_rows)

        self.sync_carousel()
        asyncio.create_task(self.load())

    async def load(self):
        await asyncio.gather(self.suwayomi.refreshLibrary(), self.suwayomi.refreshSources())
        self.reload_rows()

    def update_state(self):
        has_rows = len(self.rows) > 0
        has_library = self.suwayomi.library.get_n_items() > 0
        if has_rows or has_library:
            self.state = "home"
        else:
            self.state = "greeter"

    def on_library_changed(self):
        self.sync_carousel()
        self.update_state()

    def sync_carousel(self):
        while self.manga_carousel.get_n_pages():
            page = self.manga_carousel.get_nth_page(0)
            page.release()
            self.manga_carousel.remove(page)

        for manga in list(self.suwayomi.library)[:CAROUSEL_SIZE]:
            self.manga_carousel.append(MangaOverview(manga))

        if self.manga_carousel.get_n_pages():
            self.carousel_stack.set_visible_child_name("carousel")
        else:
            self.carousel_stack.set_visible_child_name("empty")

    def pick_sources(self) -> list:
        sources_by_extension = {}
        for source in self.suwayomi.sources:
            if source.id == LOCAL_SOURCE_ID:
                continue
            extension = source.extension_pkg_name
            if extension not in sources_by_extension:
                sources_by_extension[extension] = []
            sources_by_extension[extension].append(source)

        picked = []
        for group in sources_by_extension.values():
            picked.append(random.choice(group))
        random.shuffle(picked)
        return picked[:CANDIDATES]

    def reload_rows(self):
        if self.rows_task:
            self.rows_task.cancel()
        self.rows_task = asyncio.create_task(self.load_rows())

    async def load_row(self, source, semaphore):
        async with semaphore:
            if len(self.rows) >= MAX_ROWS:
                return
            mangas = await self.suwayomi.getSourceManga(source.id)

        if mangas and len(self.rows) < MAX_ROWS:
            row = MangaRow(source.name)
            row.set_items(mangas[:ROW_SIZE])
            self.main_box.append(row)
            self.rows.append(row)

    async def load_rows(self):
        for row in self.rows:
            self.main_box.remove(row)
        self.rows = []

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        loads = []
        for source in self.pick_sources():
            loads.append(self.load_row(source, semaphore))

        await asyncio.gather(*loads, return_exceptions=True)
        self.update_state()
