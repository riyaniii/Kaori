import asyncio
import datetime
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk


def backup_filters():
    backup_filter = Gtk.FileFilter(name=_("Backups"))
    backup_filter.add_pattern("*.tachibk")
    backup_filter.add_pattern("*.proto.gz")
    filters = Gio.ListStore(item_type=Gtk.FileFilter)
    filters.append(backup_filter)
    return filters


class BackupActions:
    def __init__(self, preferences):
        self.preferences = preferences
        self.suwayomi = Gio.Application.get_default().suwayomi

    def window(self):
        return self.preferences.get_root()

    def show_toast(self, message):
        self.preferences.add_toast(Adw.Toast(title=message))

    def create(self):
        today = datetime.date.today().isoformat()
        dialog = Gtk.FileDialog(
            title=_("Save Backup"),
            initial_name=f"kaori-{today}.tachibk",
            filters=backup_filters(),
        )
        dialog.save(self.window(), None, self.on_save_chosen)

    def on_save_chosen(self, dialog, result):
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        asyncio.create_task(self.save_backup(file.get_path()))

    async def save_backup(self, path):
        self.show_toast(_("Creating backup…"))
        try:
            data = await self.suwayomi.createBackup(None)
            with open(path, "wb") as file:
                file.write(data)
        except Exception as error:
            print("Creating the backup failed:", error)
            self.show_toast(_("Couldn't create the backup"))
            return
        self.show_toast(_("Backup saved"))

    def restore(self):
        dialog = Gtk.FileDialog(title=_("Restore Backup"), filters=backup_filters())
        dialog.open(self.window(), None, self.on_open_chosen)

    def on_open_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        asyncio.create_task(self.check_backup(file.get_path()))

    async def check_backup(self, path):
        try:
            report = await self.suwayomi.validateBackup(path)
        except Exception as error:
            print("Reading the backup failed:", error)
            self.show_toast(_("This file isn't a backup Kaori can read"))
            return

        missing = [source["name"] for source in report["missingSources"]]
        missing += [tracker["name"] for tracker in report["missingTrackers"]]
        if not missing:
            await self.restore_backup(path)
            return

        alert = Adw.AlertDialog(
            heading=_("Some Things Are Missing"),
            body=_("Install these sources or sign in to these trackers first, or their entries won't work:\n\n{}").format("\n".join(missing)),
        )
        alert.add_response("cancel", _("Cancel"))
        alert.add_response("restore", _("Restore Anyway"))
        alert.set_response_appearance("restore", Adw.ResponseAppearance.SUGGESTED)
        alert.connect("response", self.on_alert_response, path)
        alert.present(self.preferences)

    def on_alert_response(self, alert, response, path):
        if response == "restore":
            asyncio.create_task(self.restore_backup(path))

    async def restore_backup(self, path):
        toast = Adw.Toast(title=_("Restoring backup…"), timeout=0)
        self.preferences.add_toast(toast)

        def on_progress(status):
            if status["totalManga"]:
                toast.set_title(_("Restoring backup… {} of {}").format(status["mangaProgress"], status["totalManga"]))

        try:
            status = await self.suwayomi.restoreBackup(path, on_progress)
        except Exception as error:
            print("Restoring the backup failed:", error)
            status = {"state": "FAILURE"}
        toast.dismiss()

        if status["state"] == "SUCCESS":
            self.show_toast(_("Backup restored"))
        else:
            self.show_toast(_("Couldn't restore the backup"))
