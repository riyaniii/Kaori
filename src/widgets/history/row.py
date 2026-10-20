from gettext import gettext as _

from gi.repository import Gio, GObject, Gtk

from ...integrations import models
from ..chapter.row import ChapterRow
from ..common.chapter_menu import ChapterMenu
from ..common.dates import to_datetime


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/history/row.ui')
class HistoryRow(Gtk.Box):
    __gtype_name__ = "KaoriHistoryRow"
    __gsignals__ = {
        "resume": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    chapters_box = Gtk.Template.Child()

    manga = GObject.Property(type=models.Manga)
    chapter = GObject.Property(type=models.Chapter)
    chapter_count = GObject.Property(type=int, default=1)
    expanded = GObject.Property(type=bool, default=False)

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.entry = None
        self.cover_task = None
        self.bindings = []

        self.chapter_store = Gio.ListStore(item_type=models.Chapter)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_chapter_setup)
        factory.connect("bind", self.on_chapter_bind)

        self.chapter_list = Gtk.ListView(
            model=Gtk.NoSelection(model=self.chapter_store),
            factory=factory,
            single_click_activate=True,
            css_classes=["inherit-color", "navigation-sidebar"],
        )
        self.chapter_list.set_vscroll_policy(Gtk.ScrollablePolicy.NATURAL)
        self.chapter_list.connect("activate", self.on_chapter_activate)
        self.chapters_box.append(self.chapter_list)

        self.connect("notify::chapter-count", self.update_chapters)
        self.connect("notify::expanded", self.update_chapters)
        self.chapter_menu = ChapterMenu(self, lambda: self.chapter)

    def do_dispose(self):
        self.chapter_menu.close()
        Gtk.Box.do_dispose(self)

    def set_entry(self, entry):
        self.entry = entry
        self.manga = entry.manga
        self.bindings.append(entry.bind_property("chapter", self, "chapter", GObject.BindingFlags.SYNC_CREATE))
        self.bindings.append(entry.bind_property("chapter-count", self, "chapter-count", GObject.BindingFlags.SYNC_CREATE))
        self.bindings.append(entry.bind_property(
            "expanded", self, "expanded",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        ))
        self.cover_task = self.suwayomi.startThumbnail(self.manga)

    def clear_entry(self):
        for binding in self.bindings:
            binding.unbind()
        self.bindings = []
        self.suwayomi.stopThumbnail(self.manga, self.cover_task)
        self.cover_task = None
        self.entry = None
        self.expanded = False
        self.chapter_store.remove_all()

    def fill_chapters(self):
        self.chapter_store.splice(0, self.chapter_store.get_n_items(), self.entry.chapters)

    def update_chapters(self, *args):
        if self.expanded and self.entry:
            self.fill_chapters()

    def on_chapter_setup(self, factory, list_item):
        list_item.set_activatable(True)
        list_item.set_child(ChapterRow())

    def on_chapter_bind(self, factory, list_item):
        list_item.get_child().model = list_item.get_item()

    def on_chapter_activate(self, chapter_list, position):
        self.emit("resume", self.chapter_store.get_item(position))

    @Gtk.Template.Callback()
    def subtitle_text(self, obj, name, number, is_read, page_count, last_page_read):
        parts = [models.chapter_title(name, number)]

        if is_read:
            parts.append(_("Finished"))
        elif page_count > 0:
            parts.append(_("Page {} of {}").format(last_page_read + 1, page_count))
        return " · ".join(parts)

    @Gtk.Template.Callback()
    def many_chapters(self, obj, count):
        return count > 1

    @Gtk.Template.Callback()
    def count_text(self, obj, count):
        return _("{} chapters").format(count)

    @Gtk.Template.Callback()
    def expand_icon(self, obj, expanded):
        if expanded:
            return "pan-up-symbolic"
        return "pan-down-symbolic"

    @Gtk.Template.Callback()
    def time_text(self, obj, last_read_at):
        moment = to_datetime(last_read_at)
        if moment is None:
            return ""
        return f"{moment:%H:%M}"

    @Gtk.Template.Callback()
    def on_expand_clicked(self, button):
        self.expanded = not self.expanded

    @Gtk.Template.Callback()
    def on_resume_clicked(self, button):
        self.emit("resume", self.chapter)
