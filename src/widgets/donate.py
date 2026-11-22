import time

from gi.repository import Adw, Gio, Gtk

from ..constants import DONATE_URL

REMINDER_INTERVAL = 30 * 24 * 60 * 60


def reminder_due(settings) -> bool:
    last_shown = settings.get_int64('donate-reminder-at')
    return time.time() - last_shown >= REMINDER_INTERVAL


def remember_reminder(settings) -> None:
    settings.set_int64('donate-reminder-at', int(time.time()))


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/donate.ui')
class DonateDialog(Adw.Dialog):
    __gtype_name__ = 'KaoriDonateDialog'

    def __init__(self):
        super().__init__()
        remember_reminder(Gio.Application.get_default().settings)

    @Gtk.Template.Callback()
    def on_donate_clicked(self, button):
        Gtk.UriLauncher(uri=DONATE_URL).launch(self.get_root(), None, None)
        self.close()

    @Gtk.Template.Callback()
    def on_later_clicked(self, button):
        self.close()
