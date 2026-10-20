from gi.repository import Gtk, Adw, Gio, GLib
from ..manga import MangaCard
from ...integrations import models
from ...integrations.suwayomi import watch

@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/containers/manga_grid.ui')
class MangaGrid(Adw.BreakpointBin):
    __gtype_name__ = 'KaoriMangaGrid'

    grid = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.search_text = ""
        self.category_id = None
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.options = models.LibraryOptions(show_unread_badge=False)

        self.store = Gio.ListStore(item_type=models.Manga)

        self.custom_filter = Gtk.CustomFilter.new(self.filter_func)
        self.filter_model = Gtk.FilterListModel(model=self.store, filter=self.custom_filter)

        self.custom_sorter = Gtk.CustomSorter.new(self.sort_func)
        self.sort_model = Gtk.SortListModel(model=self.filter_model)

        selection = Gtk.NoSelection(model=self.sort_model)
        self.grid.set_model(selection)
        self.grid.connect('activate', self.on_activate)

        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', self.on_setup)
        factory.connect('bind', self.on_bind)
        factory.connect('unbind', self.on_unbind)
        self.grid.set_factory(factory)

        watch(self, self.suwayomi, self.refilter, "notify::category-revision")
        watch(self, self.suwayomi, self.on_library_changed, "notify::library-revision")

    def use_options(self, options):
        self.options = options
        self.sort_model.set_sorter(self.custom_sorter)
        options.connect("notify", self.on_options_changed)
        self.refilter()

    def on_options_changed(self, options, pspec):
        name = pspec.name
        if name == "sort-key" or name == "reverse":
            self.custom_sorter.changed(Gtk.SorterChange.DIFFERENT)
        elif name.startswith("filter-") or name.startswith("status-") or name == "source-id":
            self.refilter()

    def on_library_changed(self):
        self.custom_sorter.changed(Gtk.SorterChange.DIFFERENT)
        self.refilter()

    def bind_store(self, store: Gio.ListStore):
        self.store = store
        self.filter_model.set_model(store)

    def refilter(self):
        self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)

    def filter_func(self, item):
        if self.category_id is not None:
            members = self.suwayomi.category_members.get(self.category_id, set())
            if item.id not in members:
                return False
        title = (item.title or "").lower()
        if self.search_text not in title:
            return False
        return self.options.matches(item)

    def sort_func(self, first, second, *args):
        return self.options.compare_manga(first, second)

    def set_search_text(self, text: str):
        self.search_text = text.strip().lower()
        self.refilter()

    def set_category(self, category_id: int):
        if category_id < 0:
            self.category_id = None
        else:
            self.category_id = category_id
        self.refilter()

    def on_setup(self, factory, list_item):
        child = MangaCard()
        child.thumbnail_task = None
        list_item.set_child(child)

    def on_bind(self, factory, list_item):
        item = list_item.get_item()
        card = list_item.get_child()
        card.options = self.options
        card.model = item
        card.thumbnail_task = self.suwayomi.startThumbnail(item)

    def on_unbind(self, factory, list_item):
        card = list_item.get_child()
        self.suwayomi.stopThumbnail(list_item.get_item(), card.thumbnail_task)
        card.thumbnail_task = None
        card.model = None

    def on_activate(self, grid_view, position):
        item = self.sort_model.get_item(position)
        grid_view.activate_action("app.show_manga", GLib.Variant("i", item.id))

    def remove_all(self):
        self.store.remove_all()

    def set_items(self, items: list):
        self.store.splice(0, self.store.get_n_items(), items)
