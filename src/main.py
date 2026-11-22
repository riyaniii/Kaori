import asyncio
import os
import platform
import sys
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.events import GLibEventLoopPolicy

asyncio.set_event_loop_policy(GLibEventLoopPolicy())

from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from .constants import NAME, DONATE_URL, GUIDE_URL
from .integrations import Suwayomi, ConnectionFailed, LoginFailed
from .passwords import load_password, save_password, forget_password
from .server import LocalServer
from .widgets import KaoriWindow, build_shortcuts
from .widgets.preferences import KaoriPreferences
from .widgets.donate import DonateDialog, reminder_due
from .widgets.setup import SetupDialog

if sys.platform == 'linux':
    from .tray import Entry, Tray
else:
    Entry = Tray = None

APPLICATION_ID = 'io.github.riyaniii.Kaori'
METAINFO_PATH = '/io/github/riyaniii/Kaori/io.github.riyaniii.Kaori.metainfo.xml'

READY_TIMEOUT = 90
POLL_INTERVAL = 0.5
AUTOSTART_COMMAND = ['kaori', '--background']


def run_until_done(coro, timeout: float) -> None:
    task = asyncio.ensure_future(coro)
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not task.done() and time.monotonic() < deadline:
        if not context.iteration(False):
            time.sleep(0.01)
    if not task.done():
        task.cancel()


class KaoriApplication(Adw.Application):

    def __init__(self, version: str) -> None:
        super().__init__(application_id=APPLICATION_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
                         resource_base_path='/io/github/riyaniii/Kaori')
        self.version = version
        self.settings = Gio.Settings(schema_id=APPLICATION_ID)
        self.suwayomi = Suwayomi()
        self.server = LocalServer()
        self.tray = None
        self.window = None
        self.connected = False
        self.background_start = False
        self.background_held = False

        self.add_main_option('background', 0, GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE,
                             _('Start the server without opening a window'), None)
        self.connect('handle-local-options', self.on_handle_local_options)
        self.settings.connect('changed::run-in-background',
                              lambda *args: self.apply_background_settings())
        self.settings.connect('changed::run-on-startup',
                              lambda *args: self.apply_background_settings())
        self.suwayomi.connect('notify::downloader-state',
                              lambda *args: self.refresh_tray())
        self.suwayomi.download_queue.connect('items-changed',
                                             lambda *args: self.refresh_tray())

        self.create_action('quit', lambda *args: self.quit(), ['<control>q'])
        self.create_action('preferences', self.on_preferences_action, ['<control>comma'])
        self.create_action('shortcuts', self.on_shortcuts_action,
                           ['<control>question', '<control>slash'])
        self.create_action('about', self.on_about_action)
        self.create_action('donate', self.on_donate_action)
        self.create_action('change_instance', self.on_change_instance_action)

    def do_activate(self) -> None:
        background_start, self.background_start = self.background_start, False

        if self.window:
            self.window.present()
            return

        if self.connected:
            self.open_window().show_main()
            return

        mode = self.settings.get_string('suwayomi-mode')
        if mode not in ('local', 'remote'):
            self.show_setup_dialog()
            return

        hidden = (background_start
                  and sys.platform == 'linux'
                  and mode == 'local'
                  and self.settings.get_boolean('run-in-background'))

        url = self.settings.get_string('suwayomi-url')
        username = self.settings.get_string('suwayomi-username')
        password = load_password(self.login_url(mode, url), username) if username else ''

        self.hold()
        asyncio.create_task(self.launch_or_setup(mode, url, username, password, not hidden))

    def open_window(self) -> KaoriWindow:
        if self.window is None:
            self.window = KaoriWindow(application=self)
            self.window.connect('close-request', self.on_window_closed)
        self.window.present()
        return self.window

    def on_window_closed(self, window) -> bool:
        self.window = None
        return False

    def do_shutdown(self) -> None:
        run_until_done(self.suwayomi.close(), 5)
        self.set_tray(False)
        self.server.stop()
        Adw.Application.do_shutdown(self)

    def on_handle_local_options(self, app, options) -> int:
        if options.contains('background'):
            self.background_start = True
        return -1

    def local_failure_message(self) -> str:
        if self.server.log_path:
            return _("Couldn't start the local server. See the log:\n{}").format(self.server.log_path)
        return _("Couldn't start the local server. Check the logs and try again.")

    def login_url(self, mode: str, url: str) -> str:
        if mode == 'local':
            return self.server.url
        return url

    def save_login(self, mode: str, url: str, username: str, password: str) -> None:
        old_username = self.settings.get_string('suwayomi-username')
        old_url = self.login_url(self.settings.get_string('suwayomi-mode'),
                                 self.settings.get_string('suwayomi-url'))
        new_url = self.login_url(mode, url)
        if old_username and (old_username, old_url) != (username, new_url):
            forget_password(old_url, old_username)
        self.settings.set_string('suwayomi-username', username)
        if username:
            save_password(new_url, username, password)

    def change_current_login(self, username: str, password: str) -> None:
        mode = self.settings.get_string('suwayomi-mode')
        self.save_login(mode, self.settings.get_string('suwayomi-url'), username, password)

    async def launch_or_setup(self, mode: str, url: str, username: str, password: str,
                              show_window: bool = True) -> None:
        try:
            await self.launch(mode, url, username, password, show_window)
        except ConnectionFailed as error:
            if isinstance(error, LoginFailed):
                self.show_setup_dialog(error=str(error), login_for=(mode, url, username))
            else:
                self.show_setup_dialog(error=str(error))
        except Exception as error:
            print(f'[kaori] failed to start: {error!r}')
            self.server.stop()
            self.show_setup_dialog(error=_("Failed to start: {}").format(error))
        finally:
            self.release()

    async def launch(self, mode: str, url: str, username: str = '', password: str = '',
                     show_window: bool = True) -> None:
        local = mode == 'local'
        if local and not self.server.running:
            self.server.start()
        await self.suwayomi.reconnect(self.login_url(mode, url), username, password)

        try:
            await self.wait_for_server(local)
        except ConnectionFailed:
            await self.suwayomi.disconnect()
            self.server.stop()
            raise

        self.save_login(mode, url, username, password)
        self.settings.set_string('suwayomi-mode', mode)
        self.settings.set_string('suwayomi-url', '' if local else url)
        self.connected = True
        if show_window:
            self.open_window().show_main()
            self.remind_to_donate()
        self.apply_background_settings()

    async def wait_for_server(self, local: bool) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + READY_TIMEOUT
        while True:
            if self.server.exited:
                print('[kaori] server exited early')
                print('[kaori] ---- server.log (tail) ----')
                print(self.server.log_tail())
                print('[kaori] ----------------------------')
                raise ConnectionFailed(self.local_failure_message())
            try:
                await self.suwayomi.checkConnection()
                return
            except LoginFailed:
                raise
            except ConnectionFailed:
                if not local:
                    raise
            if loop.time() > deadline:
                print(f'[kaori] server did not become ready within {READY_TIMEOUT}s')
                raise ConnectionFailed(self.local_failure_message())
            await asyncio.sleep(POLL_INTERVAL)

    def set_background_hold(self, held: bool) -> None:
        if held and not self.background_held:
            self.hold()
        elif not held and self.background_held:
            self.release()
        self.background_held = held

    def set_tray(self, shown: bool) -> None:
        if Tray is None:
            return
        if shown and not self.tray:
            self.tray = Tray(APPLICATION_ID, NAME, self.tray_entries())
        elif not shown and self.tray:
            self.tray.close()
            self.tray = None

    def refresh_tray(self) -> None:
        if self.tray:
            self.tray.set_entries(self.tray_entries())

    def downloads_label(self) -> str:
        count = self.suwayomi.download_queue.get_n_items()
        if not count:
            return _('Downloads')
        if self.suwayomi.downloader_state == 'STARTED':
            return _('Downloads ({})').format(count)
        return _('Downloads ({}, paused)').format(count)

    def tray_entries(self) -> list:
        count = self.suwayomi.download_queue.get_n_items()
        running = self.suwayomi.downloader_state == 'STARTED'
        downloads = Entry(
            self.downloads_label(),
            children=[
                Entry(_('Pause Downloads') if running else _('Resume Downloads'),
                      self.toggle_downloads, running or count > 0),
                Entry(_('Clear Download Queue'), self.clear_downloads, count > 0),
            ],
        )
        return [
            Entry(_('Open Kaori'), self.activate),
            Entry(separator=True),
            downloads,
            Entry(separator=True),
            Entry(_('Open Web Interface'), self.open_web_interface),
            Entry(separator=True),
            Entry(_('Quit'), self.quit),
        ]

    def toggle_downloads(self) -> None:
        if self.suwayomi.downloader_state == 'STARTED':
            asyncio.create_task(self.suwayomi.stopDownloader())
        else:
            asyncio.create_task(self.suwayomi.startDownloader())

    def clear_downloads(self) -> None:
        asyncio.create_task(self.suwayomi.clearDownloader())

    def open_web_interface(self) -> None:
        Gio.AppInfo.launch_default_for_uri(self.suwayomi.url, None)

    def apply_background_settings(self) -> None:
        local = self.settings.get_string('suwayomi-mode') == 'local'
        background = (sys.platform == 'linux' and local
                      and self.settings.get_boolean('run-in-background'))
        autostart = background and self.settings.get_boolean('run-on-startup')

        self.set_background_hold(background)
        self.set_tray(background)
        if background:
            self.suwayomi.startPolling()
        self.sync_autostart(background, autostart)

    def sync_autostart(self, background: bool, autostart: bool) -> None:
        if sys.platform != 'linux':
            return
        if os.path.exists('/.flatpak-info'):
            self.request_background_portal(background, autostart)
        else:
            self.write_autostart_file(autostart)

    def request_background_portal(self, background: bool, autostart: bool) -> None:
        options = {
            'reason': GLib.Variant('s', _('Keep the Suwayomi server running')),
            'background': GLib.Variant('b', background),
            'autostart': GLib.Variant('b', autostart),
            'commandline': GLib.Variant('as', AUTOSTART_COMMAND),
            'dbus-activatable': GLib.Variant('b', False),
        }

        def done(bus, result):
            try:
                bus.call_finish(result)
            except GLib.Error as e:
                print("Background portal request failed:", e.message)

        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            bus.call(
                'org.freedesktop.portal.Desktop',
                '/org/freedesktop/portal/desktop',
                'org.freedesktop.portal.Background',
                'RequestBackground',
                GLib.Variant('(sa{sv})', ('', options)),
                None, Gio.DBusCallFlags.NONE, -1, None, done)
        except GLib.Error as e:
            print("Background portal unavailable:", e.message)

    def write_autostart_file(self, autostart: bool) -> None:
        path = os.path.join(GLib.get_user_config_dir(), 'autostart',
                            f'{APPLICATION_ID}.desktop')
        if autostart:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as file:
                file.write('[Desktop Entry]\n'
                           'Type=Application\n'
                           f'Name={NAME}\n'
                           f'Exec={" ".join(AUTOSTART_COMMAND)}\n'
                           'X-GNOME-Autostart-enabled=true\n')
        elif os.path.exists(path):
            os.remove(path)

    def show_setup_dialog(self, error: str | None = None, login_for: tuple | None = None) -> None:
        window = self.open_window()
        if not self.connected:
            window.show_start()
        SetupDialog(error=error, login_for=login_for).present(window)

    async def change_instance(self) -> None:
        self.connected = False
        await self.suwayomi.disconnect()
        self.server.stop()
        self.set_background_hold(False)
        self.set_tray(False)
        window = self.open_window()
        for dialog in list(window.get_dialogs()):
            dialog.force_close()
        window.show_start()
        SetupDialog().present(window)

    def on_change_instance_action(self, *args) -> None:
        asyncio.create_task(self.change_instance())

    def on_about_action(self, *args) -> None:
        asyncio.create_task(self.show_about())

    async def debug_info(self) -> str:
        server = _('Unknown')
        if self.connected:
            try:
                about = await self.suwayomi.getAboutServer()
                server = f"{about['version']} ({about['buildType']})"
            except Exception as error:
                server = _('Unavailable: {}').format(error)
        mode = self.settings.get_string('suwayomi-mode') or _('Not set up')
        lines = [
            f'Kaori: {self.version}',
            f'Suwayomi server: {server}',
            f'Connection: {mode}',
            f'Platform: {platform.platform()}',
            f'Python: {platform.python_version()}',
            f'GTK: {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}',
            f'Libadwaita: {Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}',
        ]
        if os.path.exists('/.flatpak-info'):
            lines.append('Flatpak: yes')
        return '\n'.join(lines)

    async def show_about(self) -> None:
        dialog = Adw.AboutDialog.new_from_appdata(METAINFO_PATH, self.version)
        dialog.set_version(self.version)
        dialog.set_developers(['Riyan Parvez (rini) https://github.com/riyaniii'])
        dialog.set_designers(['Riyan Parvez (rini) https://github.com/riyaniii'])
        dialog.set_translator_credits(_('translator-credits'))
        dialog.set_copyright('© 2026 Riyan Parvez')
        dialog.set_debug_info(await self.debug_info())
        dialog.set_debug_info_filename('kaori-debug-info.txt')

        dialog.add_link(_('Buy Me a Coffee'), DONATE_URL)
        dialog.add_link(_('Getting Started Guide'), GUIDE_URL)
        dialog.add_link(_('Suwayomi'), 'https://github.com/Suwayomi/Suwayomi-Server')

        dialog.add_credit_section(_('CI added by'), ['Oween Unda', 'Jaish Khan'])
        dialog.add_acknowledgement_section(_('Built With'), [
            'Suwayomi https://github.com/Suwayomi/Suwayomi-Server',
            'GTK https://gtk.org',
            'Libadwaita https://gnome.pages.gitlab.gnome.org/libadwaita/',
            'Blueprint https://gnome.pages.gitlab.gnome.org/blueprint-compiler/',
        ])
        dialog.add_acknowledgement_section(_('Inspired By'), [
            'Mihon https://mihon.app',
        ])
        dialog.add_legal_section(
            'Suwayomi Server',
            '© Suwayomi contributors',
            Gtk.License.MPL_2_0,
            None,
        )
        dialog.add_legal_section(
            _('Icons'),
            _('Some icons come from the GNOME Icon Development Kit'),
            Gtk.License.CUSTOM,
            _('These icons are dedicated to the public domain (CC0 1.0).'),
        )
        dialog.present(self.window)

    def on_donate_action(self, *args) -> None:
        if self.window:
            DonateDialog().present(self.window)

    def remind_to_donate(self) -> None:
        if self.settings.get_boolean('welcome-shown') and reminder_due(self.settings):
            GLib.timeout_add_seconds(3, self.show_donate_reminder)

    def show_donate_reminder(self) -> bool:
        if self.window and self.window.get_visible_dialog() is None:
            DonateDialog().present(self.window)
        return GLib.SOURCE_REMOVE

    def on_preferences_action(self, *args) -> None:
        if self.connected and self.window:
            KaoriPreferences().present(self.window)

    def on_shortcuts_action(self, *args) -> None:
        build_shortcuts().present(self.props.active_window)

    def create_action(self, name, callback, shortcuts=None, parameter_type=None) -> None:
        action = Gio.SimpleAction.new(name, parameter_type)
        action.connect('activate', callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f'app.{name}', shortcuts)


def main(version: str) -> int:
    return KaoriApplication(version).run(sys.argv)
