import asyncio
from gettext import gettext as _

from gi.repository import Gdk, Gio, GLib, Gtk


class ChapterMenu:
    def __init__(self, widget, get_chapter):
        self.widget = widget
        self.get_chapter = get_chapter
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.actions = Gio.SimpleActionGroup()
        widget.insert_action_group("chapter", self.actions)

        items = (
            ("add_bookmark", _("Add Bookmark"), lambda *args: self.change(is_bookmarked=True)),
            ("remove_bookmark", _("Remove Bookmark"), lambda *args: self.change(is_bookmarked=False)),
            ("mark_read", _("Mark as Read"), lambda *args: self.change(is_read=True)),
            ("mark_unread", _("Mark as Unread"), lambda *args: self.change(is_read=False)),
            ("download", _("Download"), lambda *args: asyncio.create_task(self.download())),
            ("delete_download", _("Delete Download"), lambda *args: asyncio.create_task(self.delete_download())),
        )

        menu = Gio.Menu()
        for name, label, callback in items:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.actions.add_action(action)

            item = Gio.MenuItem.new(label, "chapter." + name)
            item.set_attribute_value("hidden-when", GLib.Variant("s", "action-disabled"))
            menu.append_item(item)

        self.popover = Gtk.PopoverMenu.new_from_model(menu)
        self.popover.set_has_arrow(False)
        self.popover.set_parent(widget)

        right_click = Gtk.GestureClick(button=3)
        right_click.connect("pressed", self.on_right_click)
        widget.add_controller(right_click)

        long_press = Gtk.GestureLongPress()
        long_press.connect("pressed", self.on_long_press)
        widget.add_controller(long_press)

    def close(self):
        self.popover.unparent()

    def set_action_enabled(self, name, enabled):
        self.actions.lookup_action(name).set_enabled(enabled)

    def show_toast(self, message):
        self.widget.activate_action("app.show_toast", GLib.Variant("s", message))

    def open_menu(self, x, y):
        chapter = self.get_chapter()
        if chapter is None:
            return

        self.set_action_enabled("add_bookmark", not chapter.is_bookmarked)
        self.set_action_enabled("remove_bookmark", chapter.is_bookmarked)
        self.set_action_enabled("mark_read", not chapter.is_read)
        self.set_action_enabled("mark_unread", chapter.is_read)
        self.set_action_enabled("download", not chapter.is_downloaded)
        self.set_action_enabled("delete_download", chapter.is_downloaded)

        area = Gdk.Rectangle()
        area.x, area.y, area.width, area.height = int(x), int(y), 1, 1
        self.popover.set_pointing_to(area)
        self.popover.popup()

    def on_right_click(self, gesture, n_press, x, y):
        self.open_menu(x, y)

    def on_long_press(self, gesture, x, y):
        self.open_menu(x, y)

    def change(self, **changes):
        asyncio.create_task(self.suwayomi.updateChapter(self.get_chapter().id, **changes))

    async def download(self):
        chapter = self.get_chapter()
        await self.suwayomi.enqueueChapterDownload(chapter.id)
        self.show_toast(_("Downloading {}").format(chapter.title))

    async def delete_download(self):
        chapter = self.get_chapter()
        await self.suwayomi.deleteDownloadedChapter(chapter.id)
        self.show_toast(_("Deleted download of {}").format(chapter.title))
