import asyncio
from dataclasses import dataclass
from gi.repository import Gtk, Adw, GObject, Gio, GLib, Gdk

from ...integrations import models

from .dialog import SettingsDialog
from .single import SinglePageReader
from .webtoon import WebtoonReader
from .double import DoublePageReader

LAST_PAGE = 10**6


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

        self.readers = {}
        for r in self.READERS:
            reader = r.widget()
            reader.bind_store(self.store)
            reader.connect("chapter-requested", self.on_chapter_requested)

            self.bind_property(
                "manga_model", reader, "manga_model",
                GObject.BindingFlags.SYNC_CREATE,
            )
            self.bind_property(
                "chapter_model", reader, "chapter_model",
                GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
            )
            self.bind_property(
                "direction", reader, "direction",
                GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
            )
            self.bind_property(
                "position", reader, "position",
                GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
            )

            self.stack.add_titled_with_icon(
                reader, r.name, r.title, r.icon_name
            )
            self.readers[r.name] = reader

        self.stack.connect("notify::visible-child-name", self.on_reader_switched)

        self.active_reader = self.readers[self.stack.get_visible_child_name()]

        self.connect("notify::position", self.on_position_notify)

        action_group = Gio.SimpleActionGroup()

        next_action = Gio.SimpleAction.new("next_page", None)
        next_action.connect("activate", lambda *_: self.active_reader.next_page())
        action_group.add_action(next_action)

        previous_action = Gio.SimpleAction.new("previous_page", None)
        previous_action.connect("activate", lambda *_: self.active_reader.previous_page())
        action_group.add_action(previous_action)

        next_chapter_action = Gio.SimpleAction.new("next_chapter", None)
        next_chapter_action.connect("activate", lambda *_: self.change_chapter(1))
        action_group.add_action(next_chapter_action)

        previous_chapter_action = Gio.SimpleAction.new("previous_chapter", None)
        previous_chapter_action.connect("activate", lambda *_: self.change_chapter(-1))
        action_group.add_action(previous_chapter_action)

        self.insert_action_group("reader", action_group)


        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

        self.applying_settings = False
        self.save_settings_id = 0
        self.connect("notify::direction", self.on_setting_changed)
        self.readers["webtoon"].connect("notify::orientation", self.on_setting_changed)

        self.settings_task = asyncio.create_task(self.load_settings())
        self.connect("unrealize", self.on_unrealize)

        self.load_task = None
        self.start_load(chapter_model, resume_position=self.initial_resume_position(chapter_model))


    def initial_resume_position(self, chapter_model) -> int:
        if chapter_model.is_read or chapter_model.last_page_read <= 0:
            return 0
        return chapter_model.last_page_read - 1

    def get_adjacent_chapter(self, direction: int):
        found, index = self.manga_model.chapters.find(self.chapter_model)
        if not found:
            return None
        index += direction
        if 0 <= index < self.manga_model.chapters.get_n_items():
            return self.manga_model.chapters.get_item(index)
        return None

    def start_load(self, chapter_model, resume_position=0) -> asyncio.Task:
        if self.load_task is not None and not self.load_task.done():
            self.load_task.cancel()
        self.load_task = asyncio.create_task(
            self.load_chapter(chapter_model, resume_position=resume_position)
        )
        return self.load_task

    async def load_chapter(self, chapter_model, resume_position=0):
        self.chapter_model = chapter_model
        pages = await self.suwayomi.getChapterPages(chapter_model.id)
        self.store.splice(0, self.store.get_n_items(), pages)

        n = self.chapter_model.page_count
        self.position = max(0, min(resume_position, n - 1)) if n else 0

    async def next_chapter(self):
        chapter = self.get_adjacent_chapter(1)
        if chapter:
            await self.start_load(chapter, self.initial_resume_position(chapter))

    async def previous_chapter(self):
        chapter = self.get_adjacent_chapter(-1)
        if chapter:
            await self.start_load(chapter, self.initial_resume_position(chapter))

    def change_chapter(self, direction: int, resume_position: int | None = None):
        if self.load_task is not None and not self.load_task.done():
            return
        chapter = self.get_adjacent_chapter(direction)
        if chapter is None:
            return
        if resume_position is None:
            resume_position = self.initial_resume_position(chapter)
        self.start_load(chapter, resume_position)

    def on_chapter_requested(self, reader, direction):
        self.change_chapter(direction, LAST_PAGE if direction < 0 else None)

    def on_unrealize(self, *_):
        for task in (self.load_task, self.settings_task):
            if task is not None:
                task.cancel()  # no-op if already finished

    def switch_reader(self, name: str):
        self.stack.set_visible_child_name(name)

    def on_reader_switched(self, stack, pspec):
        self.active_reader = self.readers[stack.get_visible_child_name()]
        self.on_setting_changed()

    def on_key_pressed(self, controller, keyval, keycode, state):

        rtl = self.direction == Gtk.TextDirection.RTL

        if state & Gdk.ModifierType.CONTROL_MASK and keyval in (Gdk.KEY_Right, Gdk.KEY_Left):
            forward = (keyval == Gdk.KEY_Right) != rtl
            self.activate_action("reader.next_chapter" if forward else "reader.previous_chapter")
            return True
        if keyval == Gdk.KEY_period:
            self.activate_action("reader.next_chapter")
            return True
        if keyval == Gdk.KEY_comma:
            self.activate_action("reader.previous_chapter")
            return True

        if keyval in (Gdk.KEY_Down, Gdk.KEY_space, Gdk.KEY_Page_Down):
            self.activate_action("reader.next_page")
            return True
        if keyval == Gdk.KEY_Up or keyval == Gdk.KEY_Page_Up:
            self.activate_action("reader.previous_page")
            return True

        if keyval == Gdk.KEY_Right:
            self.activate_action("reader.previous_page" if rtl else "reader.next_page")
            return True
        if keyval == Gdk.KEY_Left:
            self.activate_action("reader.next_page" if rtl else "reader.previous_page")
            return True

        if keyval == Gdk.KEY_BackSpace:
            self.activate_action("reader.previous_page")
            return True
        if keyval == Gdk.KEY_Escape:
            self.get_root().main_nav_view.pop()
            return True

        return False

    def on_position_notify(self, *_):
        if (self.position > self.chapter_model.last_page_read):
            self.save_progress()
        else:
            return

    def save_progress(self):
        total = self.chapter_model.page_count
        if total <= 0:  # page count not loaded yet, don't mark the chapter read
            return
        seen = self.position + 1
        if self.stack.get_visible_child_name() == "double":
            seen += 1
        asyncio.create_task(
            self.suwayomi.updateChapter(
                chapter_id=self.chapter_model.id,
                is_read=seen >= total,
                last_page_read=self.position + 1,
            )
        )

    @Gtk.Template.Callback()
    def on_settings_clicked(self, *_):
        dialog = SettingsDialog(self.stack)
        dialog.present(self)

    async def load_settings(self):
        settings = await self.suwayomi.getReaderSettings(self.manga_model.id)
        self.apply_settings(settings)

    def apply_settings(self, settings):
        self.applying_settings = True
        try:
            if settings.get("mode") in self.readers:
                self.stack.set_visible_child_name(settings["mode"])
            if settings.get("orientation") in ("vertical", "horizontal"):
                self.readers["webtoon"].orientation = (
                    Gtk.Orientation.HORIZONTAL if settings["orientation"] == "horizontal"
                    else Gtk.Orientation.VERTICAL
                )
            if settings.get("direction") in ("ltr", "rtl"):
                self.direction = (
                    Gtk.TextDirection.RTL if settings["direction"] == "rtl"
                    else Gtk.TextDirection.LTR
                )
        finally:
            self.applying_settings = False

    def current_settings(self):
        return {
            "mode": self.stack.get_visible_child_name(),
            "orientation": "horizontal"
                if self.readers["webtoon"].orientation == Gtk.Orientation.HORIZONTAL else "vertical",
            "direction": "rtl" if self.direction == Gtk.TextDirection.RTL else "ltr",
        }

    def on_setting_changed(self, *_):
        if self.applying_settings:
            return
        if self.save_settings_id:
            GLib.source_remove(self.save_settings_id)
        self.save_settings_id = GLib.timeout_add(500, self.flush_settings)

    def flush_settings(self):
        self.save_settings_id = 0
        asyncio.create_task(
            self.suwayomi.setReaderSettings(self.manga_model.id, self.current_settings())
        )
        return GLib.SOURCE_REMOVE

    @Gtk.Template.Callback()
    def on_back_clicked(self, *_):
        self.get_root().main_nav_view.pop()
