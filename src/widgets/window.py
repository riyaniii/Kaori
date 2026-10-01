from gi.repository import Gtk, Adw, GLib, Gdk, Pango, GObject

import asyncio

from .. import actions
from .pages import *
from .download import DownloadsPage

from .chapter import ChapterPanel
from .manga import MangaPage
from .reader import ReaderPage

from ..constants import NAME

SWIPE_COMMIT_DISTANCE = 40.0
SWIPE_COMMIT_VELOCITY = 600.0


@Gtk.Template(resource_path='/com/rini/kaghez/window.ui')
class KaghezWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'KaghezWindow'

    name = GObject.Property(type=str)

    main_stack = Gtk.Template.Child()
    overlay_split_view = Gtk.Template.Child()
    main_nav_view = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()

    header_bar = Gtk.Template.Child()
    chapter_panel = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = NAME
        list(list(list(list(list(list(self.header_bar)[0])[0])[1])[0])[0])[0].set_ellipsize(Pango.EllipsizeMode.NONE)

        self.create_action(actions.show_manga, parameter_type="i")
        self.create_action(actions.show_reader, parameter_type="(ii)")
        self.create_action(actions.set_chapters, parameter_type="i")

        self.create_action(actions.toggle_chapter_panel, ['<control>s'], parameter_type=None)

        self.create_action(actions.show_source)
        self.create_action(actions.show_extension)
        self.create_action(actions.switch_page)
        self.create_action(actions.show_toast)

        self.create_action(actions.open_search_page, ['<control>f', '<control>k'], parameter_type=None)
        self.create_action(actions.open_downloads_page, ['<control>j'], parameter_type=None)
        self.create_action(actions.open_library_page, ['<control>l'], parameter_type=None)

        self.create_action(actions.extension_action)
        self.create_action(actions.toggle_library, parameter_type="i")

        self.create_action(actions.download_chapter, parameter_type="i")
        self.create_action(actions.delete_chapter_download, parameter_type="i")

        scroll_controller = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.HORIZONTAL
        )
        scroll_controller.connect("scroll-begin", self.on_swipe_begin)
        scroll_controller.connect("scroll", self.on_swipe_scroll)
        scroll_controller.connect("scroll-end", self.on_swipe_scroll_end)
        self.overlay_split_view.add_controller(scroll_controller)
        self.swipe_accum = 0.0
        self.swipe_start_time = 0.0

    def create_action(self, callback: callable, shortcuts: list | None = None, parameter_type: str = "s"):
        shortcuts = shortcuts or []
        def call_action(action, variant):
            app = self.get_application()
            if variant is None:
                result = callback(app)
            else:
                value = variant.unpack()
                result = callback(app, *value) if isinstance(value, tuple) else callback(app, value)
            if asyncio.iscoroutine(result):
                task = asyncio.create_task(result)
                task.add_done_callback(
                    lambda t: t.exception() and print(f"Action '{callback.__name__}' failed:", t.exception())
                )
        self.get_application().create_action(
            name=callback.__name__,
            callback=call_action,
            shortcuts=shortcuts,
            parameter_type=GLib.VariantType.new(parameter_type) if parameter_type else None
        )

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
        velocity = self.swipe_accum / elapsed  # px/s

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
