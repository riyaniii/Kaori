from gi.repository import Gtk, Adw, Gio, GObject

from ...integrations import models

@Gtk.Template(resource_path='/com/rini/kaghez/download/dialog.ui')
class DownloadDialog(Adw.Dialog):
    __gtype_name__ = "KaghezDownloadDialog"

    model = GObject.Property(type=models.Manga)

    def __init__(self, model):
        super().__init__()
        self.model = model
