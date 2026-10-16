import asyncio
import os
import subprocess
import sys
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.events import GLibEventLoopPolicy

asyncio.set_event_loop_policy(GLibEventLoopPolicy())

from gi.repository import Adw, Gio, GLib
from gql.transport.exceptions import TransportError

from .constants import NAME, set_version
from .integrations import Suwayomi
from .widgets import KaoriWindow, build_shortcuts
from .widgets.preferences import KaoriPreferences
from .widgets.setup import SetupWindow

APPLICATION_ID = 'io.github.riyaniii.Kaori'
JAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'Suwayomi-Server.jar')

LOCAL_URL = 'http://localhost:4567'
READY_TIMEOUT = 90
POLL_INTERVAL = 0.5

SERVER_CMD = [
    'java',
    '-Dsuwayomi.tachidesk.config.server.systemTrayEnabled=false',
    '-Dsuwayomi.tachidesk.config.server.initialOpenInBrowserEnabled=false',
    '-Dsuwayomi.tachidesk.config.server.kcefEnabled=false',
    '-jar', JAR,
]


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
        self.server: subprocess.Popen | None = None
        self.server_log = None

        self.create_action('quit', lambda *_: self.quit(), ['<control>q'])
        self.create_action('preferences', self.on_preferences_action, ['<control>comma'])
        self.create_action('shortcuts', self.on_shortcuts_action,
                           ['<control>question', '<control>slash'])
        self.create_action('about', self.on_about_action)
        self.create_action('change_instance', self.on_change_instance_action)

    def do_activate(self) -> None:
        if win := self.props.active_window:
            win.present()
            return

        mode = self.settings.get_string('suwayomi-mode')
        if mode not in ('local', 'remote'):
            self.show_setup_window()
            return

        self.hold()
        asyncio.create_task(
            self.launch_or_setup(mode, self.settings.get_string('suwayomi-url')))

    def do_shutdown(self) -> None:
        run_until_done(self.suwayomi.close(), 5)
        self.stop_server()
        Adw.Application.do_shutdown(self)

    def start_server(self) -> None:
        
        
        log_dir = os.path.join(GLib.get_user_cache_dir(), 'kaori')
        os.makedirs(log_dir, exist_ok=True)
        self.server_log = open(os.path.join(log_dir, 'server.log'), 'ab')
        self.server = subprocess.Popen(
            SERVER_CMD, stdout=self.server_log, stderr=subprocess.STDOUT)

    def stop_server(self) -> None:
        if self.server:
            self.server.terminate()
            self.server.wait()
            self.server = None
        if self.server_log:
            self.server_log.close()
            self.server_log = None

    async def launch_or_setup(self, mode: str, url: str) -> None:
        try:
            if not await self.launch(mode, url):
                self.show_setup_window(
                    error="Couldn't reconnect. Check your setup and try again.")
        except Exception as e:
            
            
            self.stop_server()
            self.show_setup_window(error=f"Failed to start: {e}")
        finally:
            self.release()

    async def launch(self, mode: str, url: str) -> bool:
        local = mode == 'local'
        if local:
            self.start_server()
        self.suwayomi.reconnect(LOCAL_URL if local else url)

        if not await self.wait_for_server():
            await self.suwayomi.disconnect()
            self.stop_server()
            return False

        self.settings.set_string('suwayomi-mode', mode)
        self.settings.set_string('suwayomi-url', '' if local else url)
        KaoriWindow(application=self).present()
        return True

    async def wait_for_server(self) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + READY_TIMEOUT
        while loop.time() < deadline:
            if self.server and self.server.poll() is not None:
                return False
            try:
                if await self.suwayomi.getServerSettings():
                    return True
            except (TransportError, OSError, TimeoutError):
                
                pass
            await asyncio.sleep(POLL_INTERVAL)
        return False

    def show_setup_window(self, error: str | None = None) -> None:
        SetupWindow(application=self, error=error).present()

    def on_change_instance_action(self, *args) -> None:
        self.stop_server()
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
