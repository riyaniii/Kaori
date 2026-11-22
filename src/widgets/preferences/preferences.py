import asyncio
import os
import sys
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from ...integrations import ConnectionFailed
from .backups import BackupActions
from .extension_stores import ExtensionStoresDialog
from .tracking import KaoriTrackingPreferences

MODES = (
    ("webtoon", _("Webtoon"), "view-continuous-symbolic"),
    ("single", _("Single Page"), "view-paged-symbolic"),
    ("double", _("Double Page"), "view-dual-symbolic"),
)

AUTH_MODES = ("NONE", "BASIC_AUTH", "SIMPLE_LOGIN", "UI_LOGIN")
OPDS_PATH = "/api/opds/v1.2"

DISPLAY_MODES = ("compact", "comfortable")

SWITCHES = {
    "cbz_row": "downloadAsCbz",
    "flaresolverr_fallback_row": "flareSolverrAsResponseFallback",
    "update_mangas_row": "updateMangas",
    "exclude_unread_row": "excludeUnreadChapters",
    "exclude_not_started_row": "excludeNotStarted",
    "exclude_completed_row": "excludeCompleted",
    "auto_download_skip_unread_row": "excludeEntryWithUnreadChapters",
    "auto_download_reuploads_row": "autoDownloadIgnoreReUploads",
    "backup_manga_row": "autoBackupIncludeManga",
    "backup_categories_row": "autoBackupIncludeCategories",
    "backup_chapters_row": "autoBackupIncludeChapters",
    "backup_tracking_row": "autoBackupIncludeTracking",
    "backup_history_row": "autoBackupIncludeHistory",
    "backup_client_row": "autoBackupIncludeClientData",
    "backup_server_row": "autoBackupIncludeServerSettings",
    "sync_manga_row": "syncDataManga",
    "sync_chapters_row": "syncDataChapters",
    "sync_categories_row": "syncDataCategories",
    "sync_tracking_row": "syncDataTracking",
    "sync_history_row": "syncDataHistory",
    "opds_unread_row": "opdsShowOnlyUnreadChapters",
    "opds_downloaded_row": "opdsShowOnlyDownloadedChapters",
    "opds_mark_read_row": "opdsMarkAsReadOnDownload",
    "debug_logs_row": "debugLogsEnabled",
}
EXPANDERS = {
    "flaresolverr_row": "flareSolverrEnabled",
    "proxy_row": "socksProxyEnabled",
    "auto_download_row": "autoDownloadNewChapters",
    "syncyomi_row": "syncYomiEnabled",
}
SPINS = {
    "update_interval_row": "globalUpdateInterval",
    "backup_interval_row": "backupInterval",
    "backup_retention_row": "backupTTL",
    "parallel_sources_row": "maxSourcesInParallel",
    "flaresolverr_timeout_row": "flareSolverrTimeout",
    "flaresolverr_ttl_row": "flareSolverrSessionTtl",
    "auto_download_limit_row": "autoDownloadNewChaptersLimit",
    "opds_items_row": "opdsItemsPerPage",
}
ENTRIES = {
    "backup_time_row": "backupTime",
    "flaresolverr_url_row": "flareSolverrUrl",
    "flaresolverr_session_row": "flareSolverrSessionName",
    "proxy_host_row": "socksProxyHost",
    "proxy_port_row": "socksProxyPort",
    "proxy_username_row": "socksProxyUsername",
    "proxy_password_row": "socksProxyPassword",
    "syncyomi_host_row": "syncYomiHost",
    "syncyomi_key_row": "syncYomiApiKey",
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
    update_mangas_row = Gtk.Template.Child()
    exclude_unread_row = Gtk.Template.Child()
    exclude_not_started_row = Gtk.Template.Child()
    exclude_completed_row = Gtk.Template.Child()
    auto_download_row = Gtk.Template.Child()
    auto_download_skip_unread_row = Gtk.Template.Child()
    auto_download_limit_row = Gtk.Template.Child()
    auto_download_reuploads_row = Gtk.Template.Child()
    backup_manga_row = Gtk.Template.Child()
    backup_categories_row = Gtk.Template.Child()
    backup_chapters_row = Gtk.Template.Child()
    backup_tracking_row = Gtk.Template.Child()
    backup_history_row = Gtk.Template.Child()
    backup_client_row = Gtk.Template.Child()
    backup_server_row = Gtk.Template.Child()
    auth_mode_row = Gtk.Template.Child()
    auth_username_row = Gtk.Template.Child()
    auth_password_row = Gtk.Template.Child()
    syncyomi_row = Gtk.Template.Child()
    syncyomi_host_row = Gtk.Template.Child()
    syncyomi_key_row = Gtk.Template.Child()
    sync_manga_row = Gtk.Template.Child()
    sync_chapters_row = Gtk.Template.Child()
    sync_categories_row = Gtk.Template.Child()
    sync_tracking_row = Gtk.Template.Child()
    sync_history_row = Gtk.Template.Child()
    opds_url_row = Gtk.Template.Child()
    opds_items_row = Gtk.Template.Child()
    opds_unread_row = Gtk.Template.Child()
    opds_downloaded_row = Gtk.Template.Child()
    opds_mark_read_row = Gtk.Template.Child()
    debug_logs_row = Gtk.Template.Child()

    loaded = GObject.Property(type=bool, default=False)
    local = GObject.Property(type=bool, default=False)
    mode_stack = GObject.Property(type=Gtk.Widget)

    def __init__(self):
        super().__init__()
        app = Gio.Application.get_default()
        self.app = app
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
        if settings["authMode"] in AUTH_MODES:
            self.auth_mode_row.set_selected(AUTH_MODES.index(settings["authMode"]))
        self.auth_username_row.set_text(settings["authUsername"] or "")
        self.opds_url_row.set_subtitle(self.suwayomi.url.rstrip("/") + OPDS_PATH)

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
            self.add_toast(Adw.Toast(title=_("Couldn't open the folder")))
            return
        Gtk.FileLauncher(file=Gio.File.new_for_path(path)).launch(self.get_root(), None, None)

    @Gtk.Template.Callback()
    def on_stores_activated(self, row):
        ExtensionStoresDialog().present(self)

    @Gtk.Template.Callback()
    def on_open_browser_activated(self, row):
        Gtk.UriLauncher(uri=self.suwayomi.url).launch(self.get_root(), None, None)

    def show_toast(self, message):
        self.add_toast(Adw.Toast(title=message))

    @Gtk.Template.Callback()
    def on_install_file_activated(self, row):
        apk_filter = Gtk.FileFilter(name=_("Android Packages"))
        apk_filter.add_pattern("*.apk")
        filters = Gio.ListStore(item_type=Gtk.FileFilter)
        filters.append(apk_filter)
        dialog = Gtk.FileDialog(title=_("Install Extension"), filters=filters)
        dialog.open(self.get_root(), None, self.on_apk_chosen)

    def on_apk_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        asyncio.create_task(self.install_file(file.get_path()))

    async def install_file(self, path):
        self.show_toast(_("Installing extension…"))
        try:
            await self.suwayomi.installExtensionFile(path)
        except Exception as error:
            print("Installing extension failed:", error)
            self.show_toast(_("Couldn't install the extension"))
            return
        self.show_toast(_("Extension installed"))

    @Gtk.Template.Callback()
    def on_create_backup_activated(self, row):
        BackupActions(self).create()

    @Gtk.Template.Callback()
    def on_restore_backup_activated(self, row):
        BackupActions(self).restore()

    @Gtk.Template.Callback()
    def on_save_login_activated(self, row):
        mode = AUTH_MODES[self.auth_mode_row.get_selected()]
        username = self.auth_username_row.get_text().strip()
        password = self.auth_password_row.get_text()
        if mode != "NONE" and not (username and password):
            self.show_toast(_("Enter a username and password first"))
            return
        asyncio.create_task(self.save_login(mode, username, password))

    async def save_login(self, mode, username, password):
        changes = {"authMode": mode, "authUsername": username}
        if password:
            changes["authPassword"] = password
        try:
            await self.suwayomi.setServerSettings(**changes)
        except Exception as error:
            print("Saving the login failed:", error)
            self.show_toast(_("Couldn't save the login"))
            return

        if mode == "NONE":
            username = password = ""
        self.suwayomi.setLogin(username, password)
        try:
            await self.suwayomi.checkConnection()
        except ConnectionFailed as error:
            self.show_toast(str(error))
            return

        self.app.change_current_login(username, password)
        self.auth_password_row.set_text("")
        self.show_toast(_("Login saved"))

    @Gtk.Template.Callback()
    def on_sync_now_activated(self, row):
        asyncio.create_task(self.sync_now())

    async def sync_now(self):
        try:
            result = await self.suwayomi.startSync()
        except Exception as error:
            print("Starting sync failed:", error)
            self.show_toast(_("Couldn't start syncing"))
            return
        messages = {
            "SUCCESS": _("Sync started"),
            "SYNC_IN_PROGRESS": _("A sync is already running"),
            "SYNC_DISABLED": _("Turn on SyncYomi first"),
        }
        self.show_toast(messages.get(result, result))

    @Gtk.Template.Callback()
    def on_copy_opds_clicked(self, button):
        Gdk.Display.get_default().get_clipboard().set(self.opds_url_row.get_subtitle())
        self.show_toast(_("Address copied"))

    @Gtk.Template.Callback()
    def on_clear_images_activated(self, row):
        asyncio.create_task(self.run_and_report(
            self.suwayomi.clearServerImageCache(),
            _("Image cache cleared"),
            _("Couldn't clear the image cache"),
        ))

    @Gtk.Template.Callback()
    def on_clear_cookies_activated(self, row):
        asyncio.create_task(self.run_and_report(
            self.suwayomi.clearCookiesAndCache(),
            _("Cookies cleared"),
            _("Couldn't clear cookies"),
        ))

    async def run_and_report(self, job, done_message, failed_message):
        try:
            await job
        except Exception as error:
            print(failed_message, error)
            self.show_toast(failed_message)
            return
        self.show_toast(done_message)
