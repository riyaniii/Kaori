import asyncio
import os
from gettext import gettext as _

from gi.repository import Gtk, Adw, Gio, GLib

from ..constants import GUIDE_URL
from ..integrations import ConnectionFailed, LoginFailed
from .donate import DonateDialog

LOCAL_SOURCE_URL = "https://github.com/Suwayomi/Suwayomi-Server/wiki/Local-Source"

FOLDERS = {
    "downloads_folder_row": ("downloadsPath", "downloads"),
    "local_folder_row": ("localSourcePath", "local"),
}

SETTINGS = {
    "cbz_row": "downloadAsCbz",
}


def row_key(row) -> str:
    return Gtk.Buildable.get_buildable_id(row)


def server_text(mode: str, url: str) -> str:
    if mode == "local":
        return _("Suwayomi on this computer")
    return url


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/setup.ui')
class SetupDialog(Adw.Dialog):
    __gtype_name__ = 'KaoriSetupDialog'

    toast_overlay = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    navigation = Gtk.Template.Child()
    server_page = Gtk.Template.Child()
    address_page = Gtk.Template.Child()
    login_page = Gtk.Template.Child()
    tour_page = Gtk.Template.Child()
    busy_page = Gtk.Template.Child()
    url_row = Gtk.Template.Child()
    login_avatar = Gtk.Template.Child()
    login_server_label = Gtk.Template.Child()
    username_row = Gtk.Template.Child()
    password_row = Gtk.Template.Child()
    login_error_label = Gtk.Template.Child()
    carousel = Gtk.Template.Child()
    downloads_page = Gtk.Template.Child()
    downloads_folder_row = Gtk.Template.Child()
    local_page = Gtk.Template.Child()
    local_folder_row = Gtk.Template.Child()
    back_button = Gtk.Template.Child()
    next_button = Gtk.Template.Child()

    def __init__(self, error: str | None = None, login_for: tuple | None = None):
        super().__init__()
        self.app = Gio.Application.get_default()
        self.settings = self.app.settings
        self.mode = "local"
        self.url = ""
        self.current = 0
        self.changes = {}

        for row in (self.downloads_folder_row, self.local_folder_row):
            self.update_folder_row(row)

        if login_for:
            mode, url, username = login_for
            self.show_login(mode, url, username, error)
        elif error:
            self.show_toast(error)

    def show_toast(self, message: str):
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=6))

    def open_uri(self, url: str):
        Gtk.UriLauncher(uri=url).launch(self.get_root(), None, None)

    @Gtk.Template.Callback()
    def on_local_activated(self, row):
        self.connect_to("local", "", "", "")

    @Gtk.Template.Callback()
    def on_remote_activated(self, row):
        saved_url = self.settings.get_string('suwayomi-url')
        if saved_url:
            self.url_row.set_text(saved_url)
        self.navigation.push(self.address_page)
        self.url_row.grab_focus()

    @Gtk.Template.Callback()
    def on_address_continue(self, *args):
        url = self.url_row.get_text().strip().rstrip('/')
        if url in ("", "http:", "https:"):
            return
        if not url.startswith(('http://', 'https://')):
            url = f"http://{url}"
        self.connect_to("remote", url, "", "")

    def show_login(self, mode, url, username, error=None):
        self.mode = mode
        self.url = url
        self.login_server_label.set_label(server_text(mode, url))
        self.username_row.set_text(username)
        self.password_row.set_text("")
        self.login_error_label.set_label(error or "")
        self.login_error_label.set_visible(bool(error))
        if self.navigation.get_visible_page() != self.login_page:
            self.navigation.push(self.login_page)
        if username:
            self.password_row.grab_focus()
        else:
            self.username_row.grab_focus()

    @Gtk.Template.Callback()
    def on_sign_in(self, *args):
        username = self.username_row.get_text().strip()
        if not username:
            self.username_row.grab_focus()
            return
        self.connect_to(self.mode, self.url, username, self.password_row.get_text())

    def connect_to(self, mode, url, username, password):
        if mode == "local":
            self.busy_page.set_title(_("Starting the Local Server…"))
        else:
            self.busy_page.set_title(_("Connecting…"))
        self.stack.set_visible_child_name("busy")
        asyncio.create_task(self.try_connect(mode, url, username, password))

    async def try_connect(self, mode, url, username, password):
        try:
            await self.app.launch(mode, url, username, password)
        except LoginFailed as error:
            self.stack.set_visible_child_name("pages")
            shown_error = str(error) if username else None
            self.show_login(mode, url, username, shown_error)
            return
        except ConnectionFailed as error:
            self.stack.set_visible_child_name("pages")
            self.show_toast(str(error))
            return
        except Exception as error:
            print(f'[kaori] launch raised: {error!r}')
            self.stack.set_visible_child_name("pages")
            self.show_toast(_("Failed to start: {}").format(error))
            return

        self.mode = mode
        if self.settings.get_boolean('welcome-shown'):
            self.force_close()
            return
        self.start_tour()

    def start_tour(self):
        if self.mode != "local":
            for page in (self.downloads_page, self.local_page):
                self.carousel.remove(page)
        self.stack.set_visible_child_name("pages")
        self.navigation.replace([self.tour_page])
        self.update_nav()

    def update_nav(self):
        last = self.carousel.get_n_pages() - 1
        self.back_button.set_opacity(1 if self.current > 0 else 0)
        self.back_button.set_sensitive(self.current > 0)
        self.next_button.set_label(_('Get Started') if self.current >= last else _('Next'))

    def go_to(self, index: int):
        self.carousel.scroll_to(self.carousel.get_nth_page(index), True)

    async def finish_tour(self):
        self.settings.set_boolean('welcome-shown', True)
        if self.changes:
            try:
                await self.app.suwayomi.setServerSettings(**self.changes)
            except Exception as error:
                print(f'[kaori] saving setup settings failed: {error!r}')
        window = self.get_root()
        self.force_close()
        DonateDialog().present(window)

    def folder_for(self, row) -> str:
        setting, folder_name = FOLDERS[row_key(row)]
        return self.changes.get(setting) or self.app.server.default_folder(folder_name)

    def update_folder_row(self, row):
        setting, folder_name = FOLDERS[row_key(row)]
        path = self.changes.get(setting)
        if path:
            row.set_subtitle(Gio.File.new_for_path(path).get_basename())
        else:
            row.set_subtitle(_("Default"))

    def set_folder_path(self, row, path: str):
        setting, folder_name = FOLDERS[row_key(row)]
        if path:
            self.changes[setting] = path
        else:
            self.changes.pop(setting, None)
        self.update_folder_row(row)

    @Gtk.Template.Callback()
    def on_position_changed(self, carousel, pspec):
        self.current = round(carousel.get_position())
        self.update_nav()

    @Gtk.Template.Callback()
    def on_back(self, button):
        if self.current > 0:
            self.go_to(self.current - 1)

    @Gtk.Template.Callback()
    def on_next(self, button):
        if self.current >= self.carousel.get_n_pages() - 1:
            asyncio.create_task(self.finish_tour())
        else:
            self.go_to(self.current + 1)

    @Gtk.Template.Callback()
    def on_guide(self, button):
        self.open_uri(GUIDE_URL)

    @Gtk.Template.Callback()
    def on_local_guide(self, button):
        self.open_uri(LOCAL_SOURCE_URL)

    @Gtk.Template.Callback()
    def on_switch_toggled(self, row, pspec):
        self.changes[SETTINGS[row_key(row)]] = row.get_active()

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
        self.set_folder_path(row, folder.get_path())

    @Gtk.Template.Callback()
    def on_path_cleared(self, button):
        row = button.get_ancestor(Adw.ActionRow)
        self.set_folder_path(row, "")

    @Gtk.Template.Callback()
    def on_open_folder(self, button):
        row = button.get_ancestor(Adw.ActionRow)
        path = self.folder_for(row)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            return
        Gtk.FileLauncher(file=Gio.File.new_for_path(path)).launch(self.get_root(), None, None)
