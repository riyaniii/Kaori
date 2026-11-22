from gi.repository import Gtk, Adw, Gio, GLib
from ..manga import MangaCard
from ...integrations import models
from ...integrations.suwayomi import watch
from ..common.numbers import to_number

STATUS_PROPERTIES = {
    "CANCELLED": "status_cancelled",
    "COMPLETED": "status_completed",
    "LICENSED": "status_licensed",
    "ONGOING": "status_ongoing",
    "ON_HIATUS": "status_hiatus",
    "PUBLISHING_FINISHED": "status_finished",
    "UNKNOWN": "status_unknown",
}


def chapter_time(chapter, name):
    if chapter is None:
        return 0
    return to_number(getattr(chapter, name))


def compare(first, second):
    return (first > second) - (first < second)


def title_key(manga):
    return (manga.title or "").lower()


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/containers/manga_grid.ui')
class MangaGrid(Adw.BreakpointBin):
    __gtype_name__ = 'KaoriMangaGrid'

    grid = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.search_text = ""
        self.category_id = None
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.options = models.LibraryOptions()
        self.card_options = models.CardOptions(show_unread_badge=False)

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
        self.card_options = options.card
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

    def manga_matches(self, manga):
        options = self.options
        if options.filter_unread and manga.unread_count <= 0:
            return False
        if options.filter_started and manga.last_read_chapter is None:
            return False
        if options.filter_downloaded and manga.download_count <= 0:
            return False
        if options.filter_bookmarked and manga.bookmark_count <= 0:
            return False
        if options.filter_duplicates and not manga.has_duplicate_chapters:
            return False
        if options.source_id and manga.source_id != options.source_id:
            return False

        chosen = []
        for status, name in STATUS_PROPERTIES.items():
            if getattr(options, name):
                chosen.append(status)
        if chosen and (manga.status or "UNKNOWN") not in chosen:
            return False
        return True

    def sort_number(self, manga):
        key = self.options.sort_key
        if key == "unread":
            return manga.unread_count
        if key == "total":
            return manga.total_chapters
        if key == "added":
            return to_number(manga.in_library_at)
        if key == "read":
            return chapter_time(manga.last_read_chapter, "last_read_at")
        if key == "fetched":
            return chapter_time(manga.latest_fetched_chapter, "fetched_at")
        return chapter_time(manga.latest_uploaded_chapter, "upload_date")

    def compare_manga(self, first, second):
        if self.options.sort_key == "alphabetical":
            result = compare(title_key(first), title_key(second))
        else:
            result = compare(self.sort_number(second), self.sort_number(first))
            if result == 0:
                result = compare(title_key(first), title_key(second))
        if self.options.reverse:
            result = -result
        return result

    def filter_func(self, item):
        if self.category_id is not None:
            members = self.suwayomi.category_members.get(self.category_id, set())
            if item.id not in members:
                return False
        if self.search_text not in title_key(item):
            return False
        return self.manga_matches(item)

    def sort_func(self, first, second, *args):
        return self.compare_manga(first, second)

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
        card.options = self.card_options
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
