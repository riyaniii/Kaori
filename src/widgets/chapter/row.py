from gi.repository import Gtk, GObject

from ...integrations import models
from ..common.chapter_menu import ChapterMenu
from ..common.dates import to_datetime

READ_OPACITY = 0.5


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/chapter/row.ui')
class ChapterRow(Gtk.Box):
    __gtype_name__ = "KaoriChapterRow"

    model = GObject.Property(type=models.Chapter)

    def __init__(self, model=None):
        super().__init__()
        self.model = model
        self.chapter_menu = ChapterMenu(self, lambda: self.model)

    def do_dispose(self):
        self.chapter_menu.close()
        Gtk.Box.do_dispose(self)

    @Gtk.Template.Callback()
    def get_opacity(self, obj, is_read):
        if is_read:
            return READ_OPACITY
        return 1.0

    @Gtk.Template.Callback()
    def get_formatted_upload_date(self, obj, upload_date):
        moment = to_datetime(upload_date)
        if moment is None:
            return ""
        return moment.strftime("%m/%d/%Y")

    @Gtk.Template.Callback()
    def get_formatted_read_count(self, obj, last_page_read, page_count):
        return f"{last_page_read}/{page_count}"

    @Gtk.Template.Callback()
    def get_is_reading(self, obj, last_page_read):
        return last_page_read != 0
