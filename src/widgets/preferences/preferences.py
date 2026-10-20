import asyncio
import os
import sys

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from .extension_stores import ExtensionStoresDialog

MODES = (
    ("webtoon", "Webtoon", "view-continuous-symbolic"),
    ("single", "Single Page", "view-paged-symbolic"),
    ("double", "Double Page", "view-dual-symbolic"),
)

DISPLAY_MODES = ("compact", "comfortable")

SWITCHES = {
    "cbz_row": "downloadAsCbz",
    "flaresolverr_fallback_row": "flareSolverrAsResponseFallback",
}
EXPANDERS = {
    "flaresolverr_row": "flareSolverrEnabled",
    "proxy_row": "socksProxyEnabled",
}
SPINS = {
    "update_interval_row": "globalUpdateInterval",
    "backup_interval_row": "backupInterval",
    "backup_retention_row": "backupTTL",
    "parallel_sources_row": "maxSourcesInParallel",
    "flaresolverr_timeout_row": "flareSolverrTimeout",
    "flaresolverr_ttl_row": "flareSolverrSessionTtl",
}
ENTRIES = {
    "backup_time_row": "backupTime",
    "flaresolverr_url_row": "flareSolverrUrl",
    "flaresolverr_session_row": "flareSolverrSessionName",
    "proxy_host_row": "socksProxyHost",
    "proxy_port_row": "socksProxyPort",
    "proxy_username_row": "socksProxyUsername",
    "proxy_password_row": "socksProxyPassword",
}
PATHS = {
    "location_row": "downloadsPath",
    "backup_path_row": "backupPath",
    "local_source_row": "localSourcePath",
}
COMBOS = {
    "proxy_version_row": "socksProxyVersion",
}
KEYS = SWITCHES | EXPANDERS | SPINS | ENTRIES | PATHS | COMBOS

DEFAULT_FOLDERS = {
    "downloadsPath": "downloads",
    "backupPath": "backups",
    "localSourcePath": "local",
}


def key_of(row) -> str:
    return KEYS[Gtk.Buildable.get_buildable_id(row)]


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/preferences/preferences.ui')
class KaoriPreferences(Adw.PreferencesDialog):
    __gtype_name__ = "KaoriPreferencesDialog"

    orientation_row = Gtk.Template.Child()
    direction_row = Gtk.Template.Child()
    display_mode_row = Gtk.Template.Child()
    unread_badge_row = Gtk.Template.Child()
    download_badge_row = Gtk.Template.Child()
    cbz_row = Gtk.Template.Child()
    location_row = Gtk.Template.Child()
    update_interval_row = Gtk.Template.Child()
    backup_path_row = Gtk.Template.Child()
    backup_time_row = Gtk.Template.Child()
    backup_interval_row = Gtk.Template.Child()
    backup_retention_row = Gtk.Template.Child()
    parallel_sources_row = Gtk.Template.Child()
    local_source_row = Gtk.Template.Child()
    flaresolverr_row = Gtk.Template.Child()
    flaresolverr_url_row = Gtk.Template.Child()
    flaresolverr_timeout_row = Gtk.Template.Child()
    flaresolverr_session_row = Gtk.Template.Child()
    flaresolverr_ttl_row = Gtk.Template.Child()
    flaresolverr_fallback_row = Gtk.Template.Child()
    proxy_row = Gtk.Template.Child()
    proxy_version_row = Gtk.Template.Child()
    proxy_host_row = Gtk.Template.Child()
    proxy_port_row = Gtk.Template.Child()
    proxy_username_row = Gtk.Template.Child()
    proxy_password_row = Gtk.Template.Child()
    background_group = Gtk.Template.Child()
    background_row = Gtk.Template.Child()
    startup_row = Gtk.Template.Child()

    loaded = GObject.Property(type=bool, default=False)
    local = GObject.Property(type=bool, default=False)
    mode_stack = GObject.Property(type=Gtk.Widget)

    def __init__(self):
        super().__init__()
        app = Gio.Application.get_default()
        self.suwayomi = app.suwayomi
        self.server = app.server
        self.settings = app.settings
        self.paths = {}
        self.local = self.settings.get_string('suwayomi-mode') == 'local'

        self.background_group.set_visible(sys.platform == 'linux' and self.local)
        self.settings.bind('run-in-background', self.background_row, 'active',
                           Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind('run-on-startup', self.startup_row, 'active',
                           Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind('library-show-unread-badge', self.unread_badge_row, 'active',
                           Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind('library-show-download-badge', self.download_badge_row, 'active',
                           Gio.SettingsBindFlags.DEFAULT)

        display_mode = self.settings.get_string('library-display-mode')
        if display_mode in DISPLAY_MODES:
            self.display_mode_row.set_selected(DISPLAY_MODES.index(display_mode))

        self.mode_stack = Adw.ViewStack()
        for name, title, icon in MODES:
            self.mode_stack.add_titled_with_icon(Adw.Bin(), name, title, icon)
        self.mode_stack.connect("notify::visible-child-name", self.on_reading_mode_changed)

        asyncio.create_task(self.load())

    async def load(self):
        settings, reader = await asyncio.gather(
            self.suwayomi.getServerSettings(),
            self.suwayomi.getGlobalReaderSettings(),
        )
        for name, key in SWITCHES.items():
            getattr(self, name).set_active(settings[key])
        for name, key in EXPANDERS.items():
            getattr(self, name).set_enable_expansion(settings[key])
        for name, key in SPINS.items():
            getattr(self, name).set_value(settings[key] or 0)
        for name, key in ENTRIES.items():
            getattr(self, name).set_text(settings[key] or "")
        for name, key in PATHS.items():
            self.set_path(getattr(self, name), settings[key])
        self.proxy_version_row.set_selected(int(settings["socksProxyVersion"] == 4))

        self.mode_stack.set_visible_child_name(reader.get("mode", "webtoon"))
        self.orientation_row.set_selected(int(reader.get("orientation") == "horizontal"))
        self.direction_row.set_selected(int(reader.get("direction") == "rtl"))
        self.loaded = True
        self.update_orientation_sensitivity()

    def save(self, row, value):
        if self.loaded:
            asyncio.create_task(self.suwayomi.setServerSettings(**{key_of(row): value}))

    def set_path(self, row, path):
        self.paths[key_of(row)] = path or ""
        row.set_subtitle(Gio.File.new_for_path(path).get_basename() if path else "Default")

    def update_orientation_sensitivity(self):
        self.orientation_row.set_sensitive(
            self.loaded and self.mode_stack.get_visible_child_name() == "webtoon"
        )

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
    def on_display_mode_changed(self, row, pspec):
        settings = getattr(self, "settings", None)
        if settings is None:
            return
        display_mode = DISPLAY_MODES[row.get_selected()]
        if settings.get_string('library-display-mode') != display_mode:
            settings.set_string('library-display-mode', display_mode)

    @Gtk.Template.Callback()
    def on_orientation_changed(self, row, pspec):
        self.save_reading_mode()

    @Gtk.Template.Callback()
    def on_direction_changed(self, row, pspec):
        if self.loaded:
            asyncio.create_task(self.suwayomi.setGlobalReadingDirection(
                "rtl" if row.get_selected() == 1 else "ltr"
            ))

    @Gtk.Template.Callback()
    def on_switch_toggled(self, row, pspec):
        self.save(row, row.get_active())

    @Gtk.Template.Callback()
    def on_expander_toggled(self, row, pspec):
        self.save(row, row.get_enable_expansion())

    @Gtk.Template.Callback()
    def on_spin_changed(self, row, pspec):
        self.save(row, int(row.get_value()))

    @Gtk.Template.Callback()
    def on_entry_applied(self, row):
        self.save(row, row.get_text())

    @Gtk.Template.Callback()
    def on_proxy_version_changed(self, row, pspec):
        self.save(row, 5 if row.get_selected() == 0 else 4)

    @Gtk.Template.Callback()
    def on_path_activated(self, row):
        Gtk.FileDialog(title=row.get_title()).select_folder(
            self.get_root(), None, self.on_path_selected, row
        )

    def on_path_selected(self, dialog, result, row):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        self.set_path(row, folder.get_path())
        self.save(row, folder.get_path())

    @Gtk.Template.Callback()
    def on_path_cleared(self, button):
        row = button.get_ancestor(Adw.ActionRow)
        self.set_path(row, "")
        self.save(row, "")

    @Gtk.Template.Callback()
    def on_path_opened(self, button):
        row = button.get_ancestor(Adw.ActionRow)
        key = key_of(row)
        path = self.paths.get(key)
        if not path:
            path = self.server.default_folder(DEFAULT_FOLDERS[key])
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            self.add_toast(Adw.Toast(title="Couldn't open the folder"))
            return
        Gtk.FileLauncher(file=Gio.File.new_for_path(path)).launch(self.get_root(), None, None)

    @Gtk.Template.Callback()
    def on_stores_activated(self, row):
        ExtensionStoresDialog().present(self)

    @Gtk.Template.Callback()
    def on_open_browser_activated(self, row):
        Gtk.UriLauncher(uri=self.suwayomi.url).launch(self.get_root(), None, None)
