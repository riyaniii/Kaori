import asyncio
import os
import sys
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.events import GLibEventLoopPolicy

asyncio.set_event_loop_policy(GLibEventLoopPolicy())

from gi.repository import Adw, Gio, GLib
from gql.transport.exceptions import TransportError

from .constants import NAME, DONATE_URL, set_version
from .integrations import Suwayomi
from .server import LocalServer
from .widgets import KaoriWindow, build_shortcuts
from .widgets.preferences import KaoriPreferences
from .widgets.setup import SetupWindow

if sys.platform == 'linux':
    from .tray import Entry, Tray
else:
    Entry = Tray = None

APPLICATION_ID = 'io.github.riyaniii.Kaori'

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
        self.background_start = False
        self.background_held = False

        self.add_main_option('background', 0, GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE,
                             'Start the server without opening a window', None)
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
        self.create_action('change_instance', self.on_change_instance_action)

    def do_activate(self) -> None:
        background_start, self.background_start = self.background_start, False

        if win := self.props.active_window:
            win.present()
            return

        mode = self.settings.get_string('suwayomi-mode')
        if mode not in ('local', 'remote'):
            self.show_setup_window()
            return

        hidden = (background_start
                  and sys.platform == 'linux'
                  and mode == 'local'
                  and self.settings.get_boolean('run-in-background'))

        self.hold()
        asyncio.create_task(self.launch_or_setup(
            mode, self.settings.get_string('suwayomi-url'), not hidden))

    def do_shutdown(self) -> None:
        run_until_done(self.suwayomi.close(), 5)
        self.set_tray(False)
        self.server.stop()
        Adw.Application.do_shutdown(self)

    def on_handle_local_options(self, app, options) -> int:
        if options.contains('background'):
            self.background_start = True
        return -1

    def failure_message(self, mode: str) -> str:
        if mode == 'local' and self.server.log_path:
            return f"Couldn't start the local server. See the log:\n{self.server.log_path}"
        if mode == 'local':
            return "Couldn't start the local server. Check the logs and try again."
        return "Couldn't connect. Check the address and try again."

    async def launch_or_setup(self, mode: str, url: str, show_window: bool = True) -> None:
        try:
            if not await self.launch(mode, url, show_window):
                self.show_setup_window(error=self.failure_message(mode))
        except Exception as e:
            print(f'[kaori] failed to start: {e!r}')
            self.server.stop()
            self.show_setup_window(error=f"Failed to start: {e}")
        finally:
            self.release()

    async def launch(self, mode: str, url: str, show_window: bool = True) -> bool:
        local = mode == 'local'
        if local and not self.server.running:
            self.server.start()
        await self.suwayomi.reconnect(self.server.url if local else url)

        if not await self.wait_for_server():
            await self.suwayomi.disconnect()
            self.server.stop()
            return False

        self.settings.set_string('suwayomi-mode', mode)
        self.settings.set_string('suwayomi-url', '' if local else url)
        if show_window:
            KaoriWindow(application=self).present()
        self.apply_background_settings()
        return True

    async def wait_for_server(self) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + READY_TIMEOUT
        while loop.time() < deadline:
            if self.server.exited:
                print('[kaori] server exited early')
                print('[kaori] ---- server.log (tail) ----')
                print(self.server.log_tail())
                print('[kaori] ----------------------------')
                return False
            try:
                if await self.suwayomi.getServerSettings():
                    return True
            except (TransportError, OSError, TimeoutError):
                pass
            await asyncio.sleep(POLL_INTERVAL)
        print(f'[kaori] server did not become ready within {READY_TIMEOUT}s')
        return False

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
            return 'Downloads'
        if self.suwayomi.downloader_state == 'STARTED':
            return f'Downloads ({count})'
        return f'Downloads ({count}, paused)'

    def tray_entries(self) -> list:
        count = self.suwayomi.download_queue.get_n_items()
        running = self.suwayomi.downloader_state == 'STARTED'
        downloads = Entry(
            self.downloads_label(),
            children=[
                Entry('Pause Downloads' if running else 'Resume Downloads',
                      self.toggle_downloads, running or count > 0),
                Entry('Clear Download Queue', self.clear_downloads, count > 0),
            ],
        )
        return [
            Entry('Open Kaori', self.activate),
            Entry(separator=True),
            downloads,
            Entry(separator=True),
            Entry('Open Web Interface', self.open_web_interface),
            Entry(separator=True),
            Entry('Quit', self.quit),
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
            'reason': GLib.Variant('s', 'Keep the Suwayomi server running'),
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

    def show_setup_window(self, error: str | None = None) -> None:
        SetupWindow(application=self, error=error).present()

    def on_change_instance_action(self, *args) -> None:
        self.server.stop()
        self.set_background_hold(False)
        self.set_tray(False)
        if win := self.props.active_window:
            for dialog in list(win.get_dialogs()):
                dialog.force_close()
            win.close()
        self.show_setup_window()

    def on_about_action(self, *args) -> None:
        dialog = Adw.AboutDialog(
            application_name=NAME,
            application_icon=APPLICATION_ID,
            developer_name='Riyan Parvez',
            version=self.version,
            developers=['Riyan Parvez (rini)'],
            designers=['Riyan Parvez (rini)'],
            copyright='© 2026 Riyan Parvez',
            issue_url='https://github.com/riyaniii/Kaori/issues',
            license='GPL-3.0-or-later',
            website='https://github.com/riyaniii/Kaori',
        )
        dialog.add_link("Buy Me a Coffee", DONATE_URL)
        dialog.add_credit_section(
            name="CI added by",
            people=[
                "Oween Unda",
                "Jaish Khan"
            ]
        )
        dialog.present(self.props.active_window)

    def on_preferences_action(self, *args) -> None:
        KaoriPreferences().present(self.props.active_window)

    def on_shortcuts_action(self, *args) -> None:
        build_shortcuts().present(self.props.active_window)

    def create_action(self, name, callback, shortcuts=None, parameter_type=None) -> None:
        action = Gio.SimpleAction.new(name, parameter_type)
        action.connect('activate', callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f'app.{name}', shortcuts)


def main(version: str) -> int:
    set_version(version)
    return KaoriApplication(version).run(sys.argv)
