import asyncio
import os
import signal
import sys
import traceback
from gettext import gettext as _

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.events import GLibEventLoopPolicy
asyncio.set_event_loop_policy(GLibEventLoopPolicy())

from gi.repository import Adw, Gio, GLib

from .constants import NAME, set_version
from .integrations import Suwayomi
from .widgets import KaghezWindow, build_shortcuts
from .widgets.preferences import KaghezPreferences
from .widgets.setup import SetupWindow

JAR_NAME = 'Suwayomi-Server-v2.3.2363.jar'
LOCAL_URL = 'http://localhost:4567'
READY_TIMEOUT = 10
POLL_INTERVAL = 0.5


class LocalServer:
    def __init__(self):
        self.proc: Gio.Subprocess | None = None
        self.pump: asyncio.Task | None = None

    @staticmethod
    def jar_path() -> str | None:
        pkgdatadir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(pkgdatadir, JAR_NAME)
        return path if os.path.isfile(path) else None

    def start(self) -> bool:
        if self.proc:
            return True
        jar = self.jar_path()
        if not jar:
            print('local Suwayomi server jar not found')
            return False

        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
        try:
            self.proc = launcher.spawnv([
                'java',
                '-Dsuwayomi.tachidesk.config.server.systemTrayEnabled=false',
                '-Dsuwayomi.tachidesk.config.server.initialOpenInBrowserEnabled=false',
                '-Dsuwayomi.tachidesk.config.server.kcefEnabled=false',
                '-jar', jar,
            ])
        except GLib.Error as e:
            print(f'failed to start local server: {e.message}')
            return False

        self.pump = asyncio.create_task(self._pump_output())
        return True

    def stop(self):
        if self.pump:
            self.pump.cancel()
            self.pump = None
        if self.proc:
            if self.proc.get_identifier():
                self.proc.send_signal(signal.SIGTERM)
                try:
                    self.proc.wait(None)
                except GLib.Error:
                    self.proc.force_exit()
            self.proc = None

    async def _pump_output(self):
        stream = Gio.DataInputStream.new(self.proc.get_stdout_pipe())
        try:
            while (line := await stream.read_line_async(GLib.PRIORITY_DEFAULT)[0]) is not None:
                print(f'[suwayomi] {line.decode(errors="replace")}', flush=True)
        except GLib.Error as e:
            print(f'[suwayomi] {e.message}', flush=True)


class KaghezApplication(Adw.Application):

    def __init__(self, version):
        super().__init__(application_id='com.rini.kaghez',
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
                         resource_base_path='/com/rini/kaghez')
        self.version = version
        self.settings = Gio.Settings(schema_id='com.rini.kaghez')
        self.suwayomi = Suwayomi()
        self.server = LocalServer()

        self.create_action('quit', lambda *_: self.quit(), ['<control>q'])
        self.create_action('preferences', self.on_preferences_action, ['<control>comma'])
        self.create_action('shortcuts', self.on_shortcuts_action,
                           ['<control>question', '<control>slash'])
        self.create_action('about', self.on_about_action)
        self.create_action('change_instance', self.on_change_instance_action)

    def do_activate(self):
        if win := self.props.active_window:
            win.present()
            return

        mode = self.settings.get_string('suwayomi-mode')
        if mode not in ('local', 'remote'):
            self.show_setup_window()
            return

        self.hold()
        task = asyncio.create_task(
            self.launch_or_setup(mode, self.settings.get_string('suwayomi-url')))
        task.add_done_callback(self.log_task_error)

    def do_shutdown(self):
        self.server.stop()
        self.suwayomi.cache.close()
        Adw.Application.do_shutdown(self)

    @staticmethod
    def log_task_error(task: asyncio.Task):
        if not task.cancelled() and (exc := task.exception()):
            traceback.print_exception(exc)

    async def launch_or_setup(self, mode: str, url: str):
        try:
            if not await self.launch(mode, url):
                self.show_setup_window(
                    error=_("Couldn't reconnect. Check your setup and try again."))
        finally:
            self.release()

    async def launch(self, mode: str, url: str) -> bool:
        local = mode == 'local'
        if local and not self.server.start():
            return False
        if not local and not url:
            return False

        self.suwayomi.reconnect(LOCAL_URL if local else url)

        if not await self.wait_for_server():
            if local:
                self.server.stop()
            return False

        self.settings.set_string('suwayomi-mode', mode)
        self.settings.set_string('suwayomi-url', '' if local else url)
        KaghezWindow(application=self).present()
        return True

    async def wait_for_server(self) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + READY_TIMEOUT
        while loop.time() < deadline:
            self.suwayomi.session = None  # force a fresh handshake
            if await self.suwayomi.getServerSettings():
                return True
            await asyncio.sleep(POLL_INTERVAL)
        return False

    def show_setup_window(self, error: str | None = None):
        SetupWindow(application=self, error=error).present()

    def on_change_instance_action(self, *args):
        self.server.stop()
        if win := self.props.active_window:
            for dialog in list(win.get_dialogs()):
                dialog.force_close()
            win.close()
        self.show_setup_window()

    def on_about_action(self, *args):
        Adw.AboutDialog(
            application_name=NAME,
            application_icon='com.rini.kaghez',
            developer_name='Riyan Parvez',
            version=self.version,
            # Translators: Replace "translator-credits" with your name/username.
            translator_credits=_('translator-credits'),
            developers=['Riyan Parvez (rini)'],
            designers=['Riyan Parvez (rini)'],
            copyright='© 2026 Riyan Parvez',
            issue_url='https://github.com/riyaniii/Kaghez/issues',
            license='GPL-3.0-or-later',
            website='https://github.com/riyaniii/Kaghez',
        ).present(self.props.active_window)

    def on_preferences_action(self, *args):
        KaghezPreferences().present(self.props.active_window)

    def on_shortcuts_action(self, *args):
        build_shortcuts().present(self.props.active_window)

    def create_action(self, name, callback, shortcuts=None, parameter_type=None):
        action = Gio.SimpleAction.new(name, parameter_type)
        action.connect('activate', callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f'app.{name}', shortcuts)


def main(version):
    set_version(version)
    return KaghezApplication(version).run(sys.argv)
