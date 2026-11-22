from gettext import gettext as _

from gi.repository import Gtk, Adw, Gio, GLib, GObject

from ...integrations import models
from ..common.numbers import to_number

from .list import ChapterList

WATCHED_PROPERTIES = ("is-read", "is-bookmarked", "is-downloaded", "scanlator")
CHAPTER_OPTION_NAMES = (
    "sort-key",
    "descending",
    "filter-unread",
    "filter-downloaded",
    "filter-bookmarked",
    "scanlator",
    "display-mode",
)


def compare(first, second):
    return (first > second) - (first < second)


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/chapter/panel.ui')
class ChapterPanel(Adw.NavigationPage):
    __gtype_name__ = "KaoriChapterPanel"

    chapter_list = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    empty_page = Gtk.Template.Child()
    options_dialog = Gtk.Template.Child()
    scanlator_group = Gtk.Template.Child()

    manga_model = GObject.Property(type=models.Manga)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.chapters = None
        self.items_handler = None
        self.chapter_handlers = {}
        self.scanlator_rows = []

        self.options = models.ChapterOptions()
        self.options.connect("notify", self.on_options_changed)
        self.options_dialog.insert_action_group("chapters", self.make_actions())

        self.filter = Gtk.CustomFilter.new(self.chapter_matches)
        self.sorter = Gtk.CustomSorter.new(self.compare_chapters)
        self.filter_model = Gtk.FilterListModel(filter=self.filter)
        self.sort_model = Gtk.SortListModel(model=self.filter_model, sorter=self.sorter)

        self.sort_model.connect("items-changed", lambda *args: self.update_stack())
        self.chapter_list.options = self.options
        self.chapter_list.set_chapters(self.sort_model)

    def do_dispose(self):
        self.unwatch_chapters()
        Adw.NavigationPage.do_dispose(self)

    def make_actions(self):
        group = Gio.SimpleActionGroup()
        for name in CHAPTER_OPTION_NAMES:
            group.add_action(Gio.PropertyAction.new(name, self.options, name))
        return group

    def chapter_matches(self, chapter, user_data=None):
        options = self.options
        if options.filter_unread and chapter.is_read:
            return False
        if options.filter_downloaded and not chapter.is_downloaded:
            return False
        if options.filter_bookmarked and not chapter.is_bookmarked:
            return False
        if options.scanlator and chapter.scanlator != options.scanlator:
            return False
        return True

    def sort_number(self, chapter):
        key = self.options.sort_key
        if key == "number":
            return chapter.chapter_number
        if key == "upload":
            return to_number(chapter.upload_date)
        if key == "fetched":
            return to_number(chapter.fetched_at)
        return chapter.source_order

    def compare_chapters(self, first, second, user_data=None):
        result = compare(self.sort_number(first), self.sort_number(second))
        if result == 0:
            result = compare(first.source_order, second.source_order)
        if self.options.descending:
            result = -result
        return result

    @Gtk.Template.Callback()
    def on_chapter_activated(self, chapter_list, chapter):
        chapter_list.activate_action(
            "app.show_reader",
            GLib.Variant("(ii)", (self.manga_model.id, chapter.id))
        )

    def on_options_changed(self, options, pspec):
        if pspec.name in ("sort-key", "descending"):
            self.sorter.changed(Gtk.SorterChange.DIFFERENT)
        elif pspec.name != "display-mode":
            self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def unwatch_chapters(self):
        if self.chapters is not None and self.items_handler is not None:
            self.chapters.disconnect(self.items_handler)
        for chapter, handler in self.chapter_handlers.items():
            chapter.disconnect(handler)
        self.chapter_handlers = {}
        self.items_handler = None

    def track_chapters(self):
        for chapter in self.chapters:
            if chapter not in self.chapter_handlers:
                self.chapter_handlers[chapter] = chapter.connect(
                    "notify", self.on_chapter_notify)

    def on_chapter_notify(self, chapter, pspec):
        if pspec.name in WATCHED_PROPERTIES:
            self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def on_chapters_changed(self, chapters, position, removed, added):
        self.track_chapters()

    def update_stack(self):
        total = self.chapters.get_n_items() if self.chapters is not None else 0
        if self.sort_model.get_n_items() > 0:
            self.stack.set_visible_child_name("list")
            return
        if total > 0:
            self.empty_page.set_description(_("No chapters match the filters"))
        else:
            self.empty_page.set_description(_("No Chapters"))
        self.stack.set_visible_child_name("empty")

    def add_scanlator(self, label, value, first):
        check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
        check.set_action_target_value(GLib.Variant.new_string(value))
        check.set_action_name("chapters.scanlator")
        if first is not None:
            check.set_group(first)

        row = Adw.ActionRow(title=label, activatable_widget=check)
        row.add_prefix(check)
        self.scanlator_group.add(row)
        self.scanlator_rows.append(row)
        return check

    def refresh_scanlators(self):
        for row in self.scanlator_rows:
            self.scanlator_group.remove(row)
        self.scanlator_rows = []

        names = set()
        if self.chapters is not None:
            names = set(c.scanlator for c in self.chapters if c.scanlator)

        if self.options.scanlator not in names:
            self.options.scanlator = ""

        self.scanlator_group.set_visible(len(names) > 1)
        if len(names) > 1:
            first = self.add_scanlator(_("All scanlators"), "", None)
            for name in sorted(names):
                self.add_scanlator(name, name, first)

    def set_manga_model(self, manga_model):
        self.unwatch_chapters()
        self.manga_model = manga_model
        self.chapters = manga_model.chapters
        self.options.scanlator = ""
        self.filter_model.set_model(self.chapters)
        self.items_handler = self.chapters.connect("items-changed", self.on_chapters_changed)
        self.track_chapters()
        self.update_stack()

    @Gtk.Template.Callback()
    def on_options_clicked(self, button):
        self.refresh_scanlators()
        self.options_dialog.present(self)
