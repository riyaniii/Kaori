import os
import subprocess

from gi.repository import GLib

JAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'Suwayomi-Server.jar')

COMMAND = [
    'java',
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

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def exited(self) -> bool:
        return self.process is not None and self.process.poll() is not None

    def default_folder(self, name: str) -> str:
        return os.path.join(GLib.get_user_data_dir(), 'Tachidesk', name)

    def start(self) -> None:
        log_dir = os.path.join(GLib.get_user_cache_dir(), 'kaori')
        os.makedirs(log_dir, exist_ok=True)
        self.log = open(os.path.join(log_dir, 'server.log'), 'ab')
        self.process = subprocess.Popen(
            COMMAND, stdout=self.log, stderr=subprocess.STDOUT)

    def stop(self) -> None:
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
        if self.log:
            self.log.close()
            self.log = None
