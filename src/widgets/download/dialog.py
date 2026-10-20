from gettext import gettext as _, ngettext

from gi.repository import Adw, Gtk

PRESET_COUNTS = {
    "preset_next": 1,
    "preset_next_5": 5,
    "preset_next_10": 10,
    "preset_next_25": 25,
    "preset_unread": None,
}


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/download/dialog.ui')
class DownloadDialog(Adw.Dialog):
    __gtype_name__ = "KaoriDownloadDialog"

    from_row = Gtk.Template.Child()
    to_row = Gtk.Template.Child()
    skip_read_row = Gtk.Template.Child()
    summary_row = Gtk.Template.Child()
    download_button = Gtk.Template.Child()

    ready = False

    def __init__(self, model, on_download):
        super().__init__()
        self.on_download = on_download
        self.chapters = model.sorted_chapters()
        self.total = len(self.chapters)

        self.first_unread = model.first_unread_index() + 1
        if self.first_unread > self.total:
            self.first_unread = 1

        names = Gtk.StringList()
        for chapter in self.chapters:
            names.append(chapter.title)
        self.from_row.set_model(names)
        self.to_row.set_model(names)

        self.select_range(self.first_unread, self.first_unread + 4)

    def select_range(self, start, end):
        start = max(1, min(start, self.total))
        end = max(start, min(end, self.total))
        self.ready = False
        self.from_row.set_selected(start - 1)
        self.to_row.set_selected(end - 1)
        self.ready = True
        self.update_summary()

    def get_range(self):
        start = self.from_row.get_selected() + 1
        end = self.to_row.get_selected() + 1
        return start, end

    def get_pending(self):
        start, end = self.get_range()
        skip_read = self.skip_read_row.get_active()
        pending = []
        for chapter in self.chapters[start - 1:end]:
            if chapter.is_downloaded:
                continue
            if skip_read and chapter.is_read:
                continue
            pending.append(chapter)
        return pending

    def update_summary(self):
        count = len(self.get_pending())
        if count == 0:
            self.summary_row.set_title(_("Nothing to download"))
        else:
            text = ngettext("{} chapter will be downloaded", "{} chapters will be downloaded", count)
            self.summary_row.set_title(text.format(count))
        self.download_button.set_sensitive(count > 0)

    @Gtk.Template.Callback()
    def on_preset_clicked(self, button):
        name = Gtk.Buildable.get_buildable_id(button)
        if name == "preset_all":
            self.select_range(1, self.total)
            return
        count = PRESET_COUNTS[name]
        start = self.first_unread
        if count is None:
            end = self.total
        else:
            end = start + count - 1
        self.select_range(start, end)

    @Gtk.Template.Callback()
    def on_from_changed(self, row, pspec):
        if not self.ready:
            return
        if self.from_row.get_selected() > self.to_row.get_selected():
            self.ready = False
            self.to_row.set_selected(self.from_row.get_selected())
            self.ready = True
        self.update_summary()

    @Gtk.Template.Callback()
    def on_to_changed(self, row, pspec):
        if not self.ready:
            return
        if self.to_row.get_selected() < self.from_row.get_selected():
            self.ready = False
            self.from_row.set_selected(self.to_row.get_selected())
            self.ready = True
        self.update_summary()

    @Gtk.Template.Callback()
    def on_skip_read_changed(self, row, pspec):
        if self.ready:
            self.update_summary()

    @Gtk.Template.Callback()
    def on_download_clicked(self, button):
        chapters = self.get_pending()
        self.close()
        self.on_download(chapters)
