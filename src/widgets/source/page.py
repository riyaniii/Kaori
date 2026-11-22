import asyncio
from gi.repository import Adw, Gio, GObject, Gtk

from ..manga import MangaCard
from ..containers import MangaGrid
from .filter import SourceFilter
from .settings import SourceSettingsDialog

from ...integrations import models
from ...integrations.suwayomi import SourceMangaType


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/source/page.ui')
class SourcePage(Adw.NavigationPage):
    __gtype_name__ = "KaoriSourcePage"

    model = GObject.Property(type=models.Source)

    search_entry = Gtk.Template.Child()
    filter_button = Gtk.Template.Child()

    popular_stack = Gtk.Template.Child()
    popular_grid = Gtk.Template.Child()
    popular_error = Gtk.Template.Child()

    latest_stack = Gtk.Template.Child()
    latest_grid = Gtk.Template.Child()
    latest_error = Gtk.Template.Child()

    search_stack = Gtk.Template.Child()
    search_grid = Gtk.Template.Child()
    search_error = Gtk.Template.Child()

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.search_task = None
        self.latest_task = None
        self.filter_changes = []

        self.filter_dialog = SourceFilter()
        self.filter_dialog.connect("applied", self.on_filters_applied)

        self.load_tab("popular", fetch_type=SourceMangaType.POPULAR)
        asyncio.create_task(self.load_filters())

    def load_tab(self, name: str, **query) -> asyncio.Task:
        return asyncio.create_task(self.load(
            getattr(self, f"{name}_stack"),
            getattr(self, f"{name}_grid"),
            getattr(self, f"{name}_error"),
            **query,
        ))

    async def load(self, stack: Gtk.Stack, grid, error_page: Adw.StatusPage, **query):
        stack.set_visible_child_name("loading")
        try:
            mangas = await self.suwayomi.getSourceManga(self.model.id, **query)
        except Exception as e:
            error_page.set_description(str(e))
            stack.set_visible_child_name("error")
            return
        grid.set_items(mangas)
        stack.set_visible_child_name("results" if mangas else "empty")

    async def load_filters(self):
        self.filter_dialog.set_filters(await self.suwayomi.getSourceFilters(self.model.id))

    @Gtk.Template.Callback()
    def on_page_changed(self, stack, pspec):
        if stack.get_visible_child_name() == "latest" and self.latest_task is None:
            self.latest_task = self.load_tab("latest", fetch_type=SourceMangaType.LATEST)

    @Gtk.Template.Callback()
    def is_search_page(self, obj, page_name):
        return page_name == "search"

    @Gtk.Template.Callback()
    def on_search_entry_activate(self, entry):
        self.search()

    def search(self):
        if self.search_task:
            self.search_task.cancel()
            self.search_task = None

        text = self.search_entry.get_text()
        if text or self.filter_changes:
            self.search_task = self.load_tab(
                "search",
                fetch_type=SourceMangaType.SEARCH,
                query=text or None,
                filters=self.filter_changes,
            )
        else:
            self.search_stack.set_visible_child_name("normal")
            self.search_grid.remove_all()

    def on_filters_applied(self, dialog, changes):
        self.filter_changes = changes
        if changes:
            self.filter_button.add_css_class("suggested-action")
        else:
            self.filter_button.remove_css_class("suggested-action")
        self.search()

    @Gtk.Template.Callback()
    def on_filter_clicked(self, *_):
        self.filter_dialog.present(self)

    @Gtk.Template.Callback()
    def on_settings_clicked(self, button):
        SourceSettingsDialog(self.model).present(self)
