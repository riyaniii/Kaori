import asyncio
from dataclasses import dataclass
from gi.repository import Adw, Gio, GObject, Gtk, GLib

from .extension_stores import ExtensionStoresDialog


@dataclass(frozen=True)
class ModeOption:
    name: str
    title: str
    icon_name: str


MODE_OPTIONS = [
    ModeOption("webtoon", "Webtoon", "view-continuous-symbolic"),
    ModeOption("single", "Single Page", "view-paged-symbolic"),
    ModeOption("double", "Double Page", "view-dual-symbolic"),
]


@Gtk.Template(resource_path='/com/rini/kaghez/preferences/preferences.ui')
class KaghezPreferences(Adw.PreferencesDialog):
    __gtype_name__ = "KaghezPreferencesDialog"

    cbz_row = Gtk.Template.Child()
    location_row = Gtk.Template.Child()
    orientation_row = Gtk.Template.Child()
    direction_row = Gtk.Template.Child()

    loaded = GObject.Property(type=bool, default=False)
    mode_stack = GObject.Property(type=Gtk.Widget)

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self._location_dialog = None

        self.mode_stack = Adw.ViewStack()
        for option in MODE_OPTIONS:
            self.mode_stack.add_titled_with_icon(
                Adw.Bin(), option.name, option.title, option.icon_name
            )
        self.mode_stack.connect("notify::visible-child-name", self.on_reading_mode_changed)

        asyncio.create_task(self.load())

    async def load(self):
        settings, reader = await asyncio.gather(
            self.suwayomi.getServerSettings(),
            self.suwayomi.getGlobalReaderSettings(),
        )
        self.cbz_row.set_active(settings.get("downloadAsCbz", False))
        downloads_path = settings.get("downloadsPath")

        if downloads_path:
            self.location_row.set_subtitle(
                Gio.File.new_for_path(downloads_path).get_basename()
            )
        else:
            self.location_row.set_subtitle(
                "Choose where downloaded chapters are stored"
            )

        if reader.get("mode") is not None:
            self.mode_stack.set_visible_child_name(reader["mode"])
        self.orientation_row.set_selected(1 if reader.get("orientation") == "horizontal" else 0)
        self.direction_row.set_selected(1 if reader.get("direction") == "rtl" else 0)
        self.loaded = True
        self.update_orientation_sensitivity()

    def update_orientation_sensitivity(self):
        is_webtoon = self.mode_stack.get_visible_child_name() == "webtoon"
        self.orientation_row.set_sensitive(self.loaded and is_webtoon)

    def save_reading_mode(self):
        if self.loaded:
            orientation = "horizontal" if self.orientation_row.get_selected() == 1 else "vertical"
            asyncio.create_task(self.suwayomi.setGlobalReadingMode(
                self.mode_stack.get_visible_child_name(), orientation
            ))

    def on_reading_mode_changed(self, stack, pspec):
        self.update_orientation_sensitivity()
        self.save_reading_mode()

    @Gtk.Template.Callback()
    def on_orientation_changed(self, row, pspec):
        self.save_reading_mode()

    @Gtk.Template.Callback()
    def on_location_activated(self, row):
        self._location_dialog = Gtk.FileDialog(title="Select Download Location")
        self._location_dialog.select_folder(self.get_root(), None, self.on_location_selected)

    def on_location_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        finally:
            self._location_dialog = None
        path = folder.get_path()
        if path:
            self.location_row.set_subtitle(folder.get_basename())
            asyncio.create_task(self.suwayomi.setDownloadsPath(path))

    @Gtk.Template.Callback()
    def on_direction_changed(self, row, pspec):
        if self.loaded:
            direction = "rtl" if row.get_selected() == 1 else "ltr"
            asyncio.create_task(self.suwayomi.setGlobalReadingDirection(direction))

    @Gtk.Template.Callback()
    def on_cbz_toggled(self, row, pspec):
        if self.loaded:
            asyncio.create_task(self.suwayomi.setDownloadAsCbz(row.get_active()))

    @Gtk.Template.Callback()
    def on_stores_activated(self, row):
        ExtensionStoresDialog().present(self)

    @Gtk.Template.Callback()
    def on_open_browser_activated(self, row):
        launcher = Gtk.UriLauncher(uri=self.suwayomi.url)
        launcher.launch(self.get_root(), None, None)
