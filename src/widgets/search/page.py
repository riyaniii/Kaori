import asyncio
from gi.repository import Adw, Gio, GObject, Gtk

from ..containers import MangaRow
from ...integrations.suwayomi import SourceMangaType


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/search/page.ui')
class SearchPage(Adw.NavigationPage):
    __gtype_name__ = "KaoriSearchPage"

    main_box = Gtk.Template.Child()

    state = GObject.Property(type=str, default="greeter")
    completed_sources = GObject.Property(type=int, default=0)
    total_sources = GObject.Property(type=int, default=0)

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.search_task = None

    def reset_progress(self):
        self.completed_sources = self.total_sources = 0

    @Gtk.Template.Callback()
    def get_progress(self, obj, completed, total):
        return completed / total if total else 0.0

    async def search_source(self, source, row, query):
        try:
            mangas = await self.suwayomi.getSourceManga(
                source.id, fetch_type=SourceMangaType.SEARCH, query=query
            )
        except Exception as error:
            print(f"search failed: {source.name}: {error}")
            mangas = []
        self.completed_sources += 1
        row.set_items(mangas)
        row.set_visible(bool(mangas))

    async def search(self, query):
        self.state = "result"
        await self.suwayomi.refreshSources()
        sources = list(self.suwayomi.sources)
        self.total_sources = len(sources)

        rows = [MangaRow(source.name) for source in sources]
        for row in rows:
            row.set_visible(False)
            self.main_box.append(row)

        await asyncio.gather(*(self.search_source(s, r, query) for s, r in zip(sources, rows)))
        self.reset_progress()
        if not any(row.get_visible() for row in rows):
            self.state = "empty"

    @Gtk.Template.Callback()
    def on_search_entry_activate(self, entry):
        if self.search_task:
            self.search_task.cancel()
        for child in list(self.main_box):
            self.main_box.remove(child)
        self.reset_progress()

        if text := entry.get_text():
            self.search_task = asyncio.create_task(self.search(text))
        else:
            self.state = "greeter"
