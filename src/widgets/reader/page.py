import asyncio
from dataclasses import dataclass
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ...integrations import models

from .base import LAST_PAGE, adjacent_chapter
from .dialog import SettingsDialog
from .guide import ReaderGuide
from .header import ReaderHeader
from .keys import ReaderKeys
from .progress import ReaderProgress
from .settings import ReaderSettings
from .single import SinglePageReader
from .webtoon import WebtoonReader
from .double import DoublePageReader


@dataclass(frozen=True)
class Reader:
    name: str
    title: str
    icon_name: str
    widget: type


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/reader/page.ui')
class ReaderPage(Adw.NavigationPage):
    __gtype_name__ = "KaoriReaderPage"

    manga_model = GObject.Property(type=models.Manga)
    chapter_model = GObject.Property(type=models.Chapter)
    position = GObject.Property(type=int, default=0)
    direction = GObject.Property(type=Gtk.TextDirection, default=Gtk.TextDirection.LTR)

    revealer = Gtk.Template.Child()
    header = Gtk.Template.Child()
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
        self.root_handlers = []

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

        self.keys = ReaderKeys(self)
        self.auto_hide = ReaderHeader(self)
        self.progress = ReaderProgress(self)
        self.reader_settings = ReaderSettings(self)

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

        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect("leave", self.on_focus_leave)
        self.add_controller(focus_controller)

        back_click = Gtk.GestureClick(button=8)
        back_click.connect("pressed", lambda gesture, n_press, x, y: self.go_back())
        self.add_controller(back_click)

        self.connect("notify::root", self.on_root_changed)
        self.connect("unrealize", self.on_unrealize)
        self.connect("shown", lambda page: self.restore_focus())
        self.connect("shown", lambda page: self.show_guide_once())

        self.start_load(chapter_model, resume_position=self.initial_resume_position(chapter_model))

    def show_toast(self, message):
        self.activate_action("app.show_toast", GLib.Variant("s", message))

    def on_focus_leave(self, controller):
        self.keys.release_keys()
        self.webtoon.scroller.stop_keys()

    def on_root_changed(self, *args):
        for obj, handler_id in self.root_handlers:
            obj.disconnect(handler_id)
        self.root_handlers = []
        self.keys.detach()
        self.auto_hide.detach()

        root = self.get_root()
        if root is None:
            return

        self.keys.attach(root)
        self.auto_hide.attach(root)
        self.root_handlers = [
            (root, root.connect("notify::visible-dialog", self.on_dialog_changed)),
        ]

    def on_dialog_changed(self, *args):
        root = self.get_root()
        if root is not None and root.get_visible_dialog() is None:
            GLib.idle_add(self.restore_focus)

    def toggle_fullscreen(self):
        root = self.get_root()
        if root is None:
            return
        if root.is_fullscreen():
            root.unfullscreen()
        else:
            root.fullscreen()

    @property
    def stored_chapter_id(self):
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
        try:
            pages = await self.suwayomi.getChapterPages(chapter_model.id)
        except Exception as error:
            print(f"chapter failed: {chapter_model.id}: {error}")
            self.show_toast(_("Couldn't load {}").format(chapter_model.title))
            return
        self.store.splice(0, self.store.get_n_items(), pages)

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
        self.keys.detach()
        self.auto_hide.cancel_hide()
        if self.load_task is not None:
            self.load_task.cancel()
        self.webtoon.scroller.stop_all()
        self.reader_settings.finish()
        self.progress.finish()

    def on_reader_switched(self, stack, pspec):
        self.webtoon.scroller.stop_all()
        self.active_reader = self.readers[stack.get_visible_child_name()]
        self.sync_store()
        self.reader_settings.on_changed()
        GLib.idle_add(self.restore_focus)

    def restore_focus(self):
        root = self.get_root()
        if root is not None and self.get_mapped() and root.get_visible_dialog() is None:
            if root.get_focus() is None:
                self.active_reader.child_focus(Gtk.DirectionType.TAB_FORWARD)
        return GLib.SOURCE_REMOVE

    def sync_store(self):
        chapter = self.chapter_model
        if chapter is None or chapter.id == self.stored_chapter_id:
            return
        if self.active_reader is self.webtoon or self.loading():
            return
        self.start_load(chapter, resume_position=self.position)

    def on_position_notify(self, page, pspec):
        self.progress.update()

    @Gtk.Template.Callback()
    def on_settings_clicked(self, *args):
        SettingsDialog(self.stack).present(self)

    @Gtk.Template.Callback()
    def on_back_clicked(self, *args):
        self.go_back()

    def go_back(self):
        self.get_root().main_nav_view.pop()

    def show_guide_once(self):
        settings = Gio.Application.get_default().settings
        if settings.get_boolean('reader-tutorial-shown'):
            return
        settings.set_boolean('reader-tutorial-shown', True)
        ReaderGuide().present(self)
