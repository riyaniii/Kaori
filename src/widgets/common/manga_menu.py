import asyncio
from gettext import gettext as _

from gi.repository import Gdk, Gio, GLib, Gtk

from ..download.dialog import DownloadDialog


class MangaMenu:
    def __init__(self, widget, get_manga):
        self.widget = widget
        self.get_manga = get_manga
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.actions = Gio.SimpleActionGroup()
        widget.insert_action_group("manga_menu", self.actions)

        items = (
            ("edit_categories", _("Edit Categories"), self.on_edit_categories),
            ("download", _("Download"), self.on_download),
            ("remove", _("Remove from Library"), self.on_remove),
            ("add", _("Add to Library"), self.on_add),
        )

        menu = Gio.Menu()
        for name, label, callback in items:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.actions.add_action(action)

            item = Gio.MenuItem.new(label, "manga_menu." + name)
            item.set_attribute_value("hidden-when", GLib.Variant("s", "action-disabled"))
            menu.append_item(item)

        self.popover = Gtk.PopoverMenu.new_from_model(menu)
        self.popover.set_has_arrow(False)
        self.popover.set_parent(widget)
        self.popover.set_halign(Gtk.Align.START)

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
        manga = self.get_manga()
        if manga is None:
            return

        self.set_action_enabled("edit_categories", manga.in_library)
        self.set_action_enabled("download", manga.in_library)
        self.set_action_enabled("remove", manga.in_library)
        self.set_action_enabled("add", not manga.in_library)

        area = Gdk.Rectangle()
        area.x, area.y, area.width, area.height = int(x), int(y), 1, 1
        self.popover.set_pointing_to(area)
        self.popover.popup()

    def on_right_click(self, gesture, n_press, x, y):
        self.open_menu(x, y)

    def on_long_press(self, gesture, x, y):
        self.open_menu(x, y)

    def on_edit_categories(self, *args):
        self.widget.activate_action("app.edit_categories", GLib.Variant("i", self.get_manga().id))

    def on_download(self, *args):
        asyncio.create_task(DownloadDialog.choose(self.get_manga(), self.widget))

    def on_remove(self, *args):
        asyncio.create_task(self.set_library(False))

    def on_add(self, *args):
        asyncio.create_task(self.set_library(True))

    async def set_library(self, in_library):
        manga = self.get_manga()
        await self.suwayomi.setMangaLibrary(manga.id, in_library)
        if in_library:
            self.show_toast(_("{} added to library").format(manga.title))
        else:
            self.show_toast(_("{} removed from library").format(manga.title))
