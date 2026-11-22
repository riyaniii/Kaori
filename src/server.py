import os
import subprocess
import sys

from gi.repository import GLib

STOP_TIMEOUT = 10

JAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'Suwayomi-Server.jar')


def java_executable() -> str:
    home = os.environ.get('JAVA_HOME')
    if home:
        candidate = os.path.join(home, 'bin', 'java')
        if os.path.isfile(candidate):
            return candidate
    return 'java'


COMMAND = [
    java_executable(),
    '-Dsuwayomi.tachidesk.config.server.systemTrayEnabled=false',
    '-Dsuwayomi.tachidesk.config.server.initialOpenInBrowserEnabled=false',
    '-Dsuwayomi.tachidesk.config.server.kcefEnabled=false',
    '-jar', JAR,
]


class LocalServer:
    url = 'http://localhost:4567'

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.log = None
        self.log_path: str | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def exited(self) -> bool:
        return self.process is not None and self.process.poll() is not None

    def default_folder(self, name: str) -> str:
        if sys.platform == 'darwin':
            base = os.path.expanduser('~/Library/Application Support')
        else:
            base = GLib.get_user_data_dir()
        return os.path.join(base, 'Tachidesk', name)

    def start(self) -> None:
        log_dir = os.path.join(GLib.get_user_cache_dir(), 'kaori')
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, 'server.log')
        print('[kaori] launching local Suwayomi server')
        print(f'[kaori]   command: {" ".join(COMMAND)}')
        print(f'[kaori]   jar:     {JAR} exists={os.path.exists(JAR)}')
        print(f'[kaori]   java:    {COMMAND[0]}')
        print(f'[kaori]   log:     {self.log_path}')
        self.log = open(self.log_path, 'ab')
        self.process = subprocess.Popen(
            COMMAND, stdout=self.log, stderr=subprocess.STDOUT)
        print(f'[kaori]   pid:     {self.process.pid}')

    def log_tail(self, lines: int = 40) -> str:
        if not self.log_path:
            return ''
        try:
            with open(self.log_path, 'rb') as handle:
                rows = handle.read().splitlines()
        except OSError:
            return ''
        return b'\n'.join(rows[-lines:]).decode('utf-8', 'replace')

    def stop(self) -> None:
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
        if self.log:
            self.log.close()
            self.log = None
