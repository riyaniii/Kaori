import asyncio
from dataclasses import dataclass

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from ...integrations import models

from .base import adjacent_chapter
from .dialog import SettingsDialog
from .single import SinglePageReader
from .webtoon import WebtoonReader
from .double import DoublePageReader

LAST_PAGE = 10**6
SETTINGS_SAVE_DELAY = 500  # ms

ORIENTATIONS = {
    "vertical": Gtk.Orientation.VERTICAL,
    "horizontal": Gtk.Orientation.HORIZONTAL,
}
DIRECTIONS = {
    "ltr": Gtk.TextDirection.LTR,
    "rtl": Gtk.TextDirection.RTL,
}


@dataclass(frozen=True)
class Reader:
    name: str
    title: str
    icon_name: str
    widget: type


@Gtk.Template(resource_path='/com/rini/kaghez/reader/page.ui')
class ReaderPage(Adw.NavigationPage):
    __gtype_name__ = "KaghezReaderPage"

    manga_model = GObject.Property(type=models.Manga)
    chapter_model = GObject.Property(type=models.Chapter)
    position = GObject.Property(type=int, default=0)
    direction = GObject.Property(type=Gtk.TextDirection, default=Gtk.TextDirection.LTR)

    stack = Gtk.Template.Child()

    READERS = [
        Reader("webtoon", "Webtoon", "view-continuous-symbolic", WebtoonReader),
        Reader("single", "Single Page", "view-paged-symbolic", SinglePageReader),
        Reader("double", "Double Page", "view-dual-symbolic", DoublePageReader),
    ]

    def __init__(self, manga_model, chapter_model):
        super().__init__()
        self.manga_model = manga_model
        self.suwayomi = Gio.Application.get_default().suwayomi

        self.store = Gio.ListStore(item_type=models.Page)
        self.load_task = None
        self.saved_pages = {}  # chapter id -> highest page (1-based) saved

        sync = GObject.BindingFlags.SYNC_CREATE
        both_ways = sync | GObject.BindingFlags.BIDIRECTIONAL

        self.readers = {}
        for info in self.READERS:
            reader = info.widget()
            reader.bind_store(self.store)
            reader.connect("chapter-requested", self.on_chapter_requested)

            self.bind_property("manga-model", reader, "manga-model", sync)
            for name in ("chapter-model", "direction", "position"):
                self.bind_property(name, reader, name, both_ways)

            self.stack.add_titled_with_icon(reader, info.name, info.title, info.icon_name)
            self.readers[info.name] = reader

        self.webtoon = self.readers["webtoon"]
        self.active_reader = self.readers[self.stack.get_visible_child_name()]
        self.stack.connect("notify::visible-child-name", self.on_reader_switched)

        self.connect("notify::position", self.on_position_notify)

        actions = {
            "next_page": lambda action, param: self.active_reader.next_page(),
            "previous_page": lambda action, param: self.active_reader.previous_page(),
            "next_chapter": lambda action, param: self.change_chapter(1),
            "previous_chapter": lambda action, param: self.change_chapter(-1),
        }
        action_group = Gio.SimpleActionGroup()
        for name, callback in actions.items():
            action = Gio.SimpleAction(name=name)
            action.connect("activate", callback)
            action_group.add_action(action)
        self.insert_action_group("reader", action_group)

        # capture phase, otherwise the scrolled windows consume arrows and page keys first
        key_controller = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self.on_key_pressed)
        key_controller.connect("key-released", self.on_key_released)
        self.add_controller(key_controller)

        # a release is never delivered if focus leaves while a key is held
        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect("leave", lambda controller: self.webtoon.stop_scrolling())
        self.add_controller(focus_controller)

        # can-pop is off so the nav view's own back gestures never fire here
        back_click = Gtk.GestureClick(button=8)
        back_click.connect("pressed", lambda gesture, n_press, x, y: self.go_back())
        self.add_controller(back_click)

        self.applying_settings = False
        self.settings_loaded = False
        self.save_settings_id = 0
        self.connect("notify::direction", self.on_setting_changed)
        self.webtoon.connect("notify::orientation", self.on_setting_changed)

        self.settings_task = asyncio.create_task(self.load_settings())
        self.connect("unrealize", self.on_unrealize)
        self.connect("shown", lambda page: self.restore_focus())

        self.start_load(chapter_model, resume_position=self.initial_resume_position(chapter_model))

    @property
    def stored_chapter_id(self):
        """The chapter `self.store` holds, read from its pages."""
        first = self.store.get_item(0)
        return first.chapter_id if first else None

    def loading(self) -> bool:
        return self.load_task is not None and not self.load_task.done()

    def initial_resume_position(self, chapter_model) -> int:
        if chapter_model.is_read or chapter_model.last_page_read <= 0:
            return 0
        return chapter_model.last_page_read - 1

    def start_load(self, chapter_model, resume_position=0) -> asyncio.Task:
        if self.loading():
            self.load_task.cancel()
        self.load_task = asyncio.create_task(
            self.load_chapter(chapter_model, resume_position=resume_position)
        )
        return self.load_task

    async def load_chapter(self, chapter_model, resume_position=0):
        self.chapter_model = chapter_model
        pages = await self.suwayomi.getChapterPages(chapter_model.id)
        self.store.splice(0, self.store.get_n_items(), pages)

        # The webtoon reader can move chapter_model while we were fetching;
        # don't yank the position around if it did.
        if self.chapter_model is None or self.chapter_model.id != chapter_model.id:
            return

        count = chapter_model.page_count
        self.position = max(0, min(resume_position, count - 1)) if count else 0

    def change_chapter(self, direction: int, resume_position: int | None = None):
        if self.loading():
            return
        chapter = adjacent_chapter(self.manga_model, self.chapter_model, direction)
        if chapter is None:
            return
        if resume_position is None:
            resume_position = self.initial_resume_position(chapter)
        self.start_load(chapter, resume_position)

    def on_chapter_requested(self, reader, direction):
        self.change_chapter(direction, LAST_PAGE if direction < 0 else None)

    def on_unrealize(self, page):
        for task in (self.load_task, self.settings_task):
            if task is not None:
                task.cancel()  # no-op if already finished
        # Don't lose a settings change made just before leaving.
        if self.save_settings_id:
            GLib.source_remove(self.save_settings_id)
            self.flush_settings()

    def on_reader_switched(self, stack, pspec):
        self.active_reader = self.readers[stack.get_visible_child_name()]
        self.sync_store()
        self.on_setting_changed()
        GLib.idle_add(self.restore_focus)

    def restore_focus(self):
        root = self.get_root()
        if root is not None and root.get_focus() is None:
            self.active_reader.child_focus(Gtk.DirectionType.TAB_FORWARD)
        return GLib.SOURCE_REMOVE

    def sync_store(self):
        chapter = self.chapter_model
        if chapter is None or chapter.id == self.stored_chapter_id:
            return
        if self.active_reader is self.webtoon or self.loading():
            return  # the webtoon has its own store
        self.start_load(chapter, resume_position=self.position)

    def on_key_pressed(self, controller, keyval, keycode, state):
        rtl = self.direction == Gtk.TextDirection.RTL
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if keyval == Gdk.KEY_Escape:
            self.go_back()
            return True

        if ctrl and keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.active_reader.zoom_in()
            return True
        if ctrl and keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.active_reader.zoom_out()
            return True
        if ctrl and keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.active_reader.reset_zoom()
            return True

        if ctrl and keyval in (Gdk.KEY_Right, Gdk.KEY_Left):
            forward = (keyval == Gdk.KEY_Right) != rtl
            self.change_chapter(1 if forward else -1)
            return True
        if keyval == Gdk.KEY_period:
            self.change_chapter(1)
            return True
        if keyval == Gdk.KEY_comma:
            self.change_chapter(-1)
            return True

        if keyval == Gdk.KEY_Home:
            self.active_reader.position = 0
            return True
        if keyval == Gdk.KEY_End:
            self.active_reader.position = LAST_PAGE
            return True

        if self.active_reader is self.webtoon:
            return self.on_webtoon_key_pressed(keyval)

        if keyval in (Gdk.KEY_Down, Gdk.KEY_space, Gdk.KEY_Page_Down):
            self.active_reader.next_page()
            return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Page_Up, Gdk.KEY_BackSpace):
            self.active_reader.previous_page()
            return True

        if keyval in (Gdk.KEY_Right, Gdk.KEY_Left):
            forward = (keyval == Gdk.KEY_Right) != rtl
            if forward:
                self.active_reader.next_page()
            else:
                self.active_reader.previous_page()
            return True

        return False

    def on_key_released(self, controller, keyval, keycode, state):
        if self.scroll_direction(keyval) == self.webtoon.scroll_direction:
            self.webtoon.stop_scrolling()

    def scroll_direction(self, keyval):
        horizontal = self.webtoon.orientation == Gtk.Orientation.HORIZONTAL
        keys = (Gdk.KEY_Left, Gdk.KEY_Right) if horizontal else (Gdk.KEY_Up, Gdk.KEY_Down)
        if keyval not in keys:
            return 0
        forward = keyval in (Gdk.KEY_Down, Gdk.KEY_Right)
        if horizontal and self.direction == Gtk.TextDirection.RTL:
            forward = not forward
        return 1 if forward else -1

    def on_webtoon_key_pressed(self, keyval):
        if keyval == Gdk.KEY_Page_Down:
            self.webtoon.scroll_page(1)
        elif keyval == Gdk.KEY_Page_Up:
            self.webtoon.scroll_page(-1)
        elif direction := self.scroll_direction(keyval):
            self.webtoon.start_scrolling(direction)
        return True  # swallow every other key so webtoon never page-turns

    def on_position_notify(self, page, pspec):
        chapter = self.chapter_model
        if chapter is None or self.loading():
            return  # position changes during a load are resume/restore, not reading
        saved = max(self.saved_pages.get(chapter.id, 0), chapter.last_page_read)
        if self.position + 1 > saved:
            self.save_progress()

    def save_progress(self):
        chapter = self.chapter_model
        total = chapter.page_count
        if total <= 0:  # page count not loaded yet, don't mark the chapter read
            return
        page = self.position + 1
        seen = self.position + self.active_reader.step
        self.saved_pages[chapter.id] = page
        asyncio.create_task(
            self.suwayomi.updateChapter(
                chapter_id=chapter.id,
                # never flip an already read chapter back to unread when rereading
                is_read=chapter.is_read or seen >= total,
                last_page_read=page,
            )
        )

    @Gtk.Template.Callback()
    def on_settings_clicked(self, *args):
        SettingsDialog(self.stack).present(self)

    async def load_settings(self):
        try:
            settings = await self.suwayomi.getReaderSettings(self.manga_model.id)
        except Exception:
            settings = {}
        self.apply_settings(settings or {})
        self.settings_loaded = True

    def apply_settings(self, settings):
        self.applying_settings = True
        try:
            if settings.get("mode") in self.readers:
                self.stack.set_visible_child_name(settings["mode"])
            if settings.get("orientation") in ORIENTATIONS:
                self.webtoon.orientation = ORIENTATIONS[settings["orientation"]]
            if settings.get("direction") in DIRECTIONS:
                self.direction = DIRECTIONS[settings["direction"]]
        finally:
            self.applying_settings = False

    def current_settings(self):
        return {
            "mode": self.stack.get_visible_child_name(),
            "orientation": self.webtoon.orientation.value_nick,
            "direction": self.direction.value_nick,
        }

    def on_setting_changed(self, *args):
        # Ignore changes until the saved settings are applied, otherwise the
        # defaults would overwrite them.
        if self.applying_settings or not self.settings_loaded:
            return
        if self.save_settings_id:
            GLib.source_remove(self.save_settings_id)
        self.save_settings_id = GLib.timeout_add(SETTINGS_SAVE_DELAY, self.flush_settings)

    def flush_settings(self):
        self.save_settings_id = 0
        asyncio.create_task(self.suwayomi.setReaderSettings(self.manga_model.id, self.current_settings()))
        return GLib.SOURCE_REMOVE

    @Gtk.Template.Callback()
    def on_back_clicked(self, *args):
        self.go_back()

    def go_back(self):
        self.get_root().main_nav_view.pop()
