from gi.repository import Adw, Gtk


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/reader/guide.ui')
class ReaderGuide(Adw.Dialog):
    __gtype_name__ = "KaoriReaderGuide"

    @Gtk.Template.Callback()
    def on_done_clicked(self, button):
        self.close()
