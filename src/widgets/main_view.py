import asyncio

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from .download import DownloadsPage
from .updates import UpdatesPage
from .history import HistoryPage
from .search import SearchPage
from .library import LibraryPage, CategoryPanel

from .chapter import ChapterPanel
from .manga import MangaPage
from .reader import ReaderPage

SWIPE_COMMIT_DISTANCE = 40.0
SWIPE_COMMIT_VELOCITY = 600.0


def find_title_label(widget):
    child = widget.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.Label) and child.has_css_class("title"):
            return child
        found = find_title_label(child)
        if found is not None:
            return found
        child = child.get_next_sibling()
    return None


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/main_view.ui')
class KaoriMainView(Adw.BreakpointBin):
    __gtype_name__ = 'KaoriMainView'

    downloads = GObject.Property(type=Gio.ListStore)
    downloading = GObject.Property(type=bool, default=False)
    extension_updates = GObject.Property(type=int, default=0)
    new_updates = GObject.Property(type=int, default=0)

    main_stack = Gtk.Template.Child()
    category_split_view = Gtk.Template.Child()
    category_panel = Gtk.Template.Child()
    overlay_split_view = Gtk.Template.Child()
    main_nav_view = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    header_bar = Gtk.Template.Child()
    chapter_panel = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = Gio.Application.get_default()
        self.settings = app.settings
        self.suwayomi = app.suwayomi
        self.downloads = self.suwayomi.download_queue
        self.suwayomi.bind_property(
            'downloader-state', self, 'downloading',
            GObject.BindingFlags.SYNC_CREATE,
            lambda binding, state: state == 'STARTED')
        self.suwayomi.bind_property('extension-updates', self, 'extension-updates',
                                    GObject.BindingFlags.SYNC_CREATE)
        self.suwayomi.bind_property('new-updates', self, 'new-updates',
                                    GObject.BindingFlags.SYNC_CREATE)
        self.suwayomi.connect('notify::new-updates', lambda *args: self.mark_updates_seen())

        self.suwayomi.updates_seen_at = self.settings.get_string('updates-seen-at')
        self.suwayomi.runInBackground(self.suwayomi.countNewUpdates())

        title_label = find_title_label(self.header_bar)
        if title_label is not None:
            title_label.set_ellipsize(Pango.EllipsizeMode.NONE)

        self.category_panel.connect(
            "activated", lambda *args: self.category_split_view.set_show_sidebar(False))

        scroll_controller = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.HORIZONTAL
        )
        scroll_controller.connect("scroll-begin", self.on_swipe_begin)
        scroll_controller.connect("scroll", self.on_swipe_scroll)
        scroll_controller.connect("scroll-end", self.on_swipe_scroll_end)
        self.overlay_split_view.add_controller(scroll_controller)
        self.swipe_accum = 0.0
        self.swipe_start_time = 0.0

    def mark_updates_seen(self):
        if self.main_stack.get_visible_child_name() == "updates" and self.suwayomi.new_updates:
            asyncio.create_task(self.save_updates_seen())

    async def save_updates_seen(self):
        try:
            seen_at = await self.suwayomi.markUpdatesSeen()
        except Exception as error:
            print("Marking updates as seen failed:", error)
            return
        self.settings.set_string('updates-seen-at', seen_at)

    @Gtk.Template.Callback()
    def on_page_changed(self, stack, pspec):
        self.mark_updates_seen()

    def on_swipe_begin(self, controller):
        self.swipe_accum = 0.0
        self.swipe_start_time = GLib.get_monotonic_time() / 1_000_000

    def on_swipe_scroll(self, controller, dx, dy):
        self.swipe_accum += dx

        if self.overlay_split_view.get_show_sidebar():
            return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def on_swipe_scroll_end(self, controller):
        now = GLib.get_monotonic_time() / 1_000_000
        elapsed = max(now - self.swipe_start_time, 1e-3)
        velocity = self.swipe_accum / elapsed

        far_enough = abs(self.swipe_accum) > SWIPE_COMMIT_DISTANCE
        fast_enough = abs(velocity) > SWIPE_COMMIT_VELOCITY

        if far_enough or fast_enough:
            opening = self.swipe_accum > 0 if far_enough else velocity > 0

            current_page = self.main_stack.get_visible_child().get_visible_page()
            maybe_reader = self.main_nav_view.get_visible_page()

            if isinstance(current_page, MangaPage) and not isinstance(maybe_reader, ReaderPage):
                self.overlay_split_view.set_show_sidebar(opening)
            else:
                return

        self.swipe_accum = 0.0
