from gi.repository import Gtk, GObject

from ...integrations import models

@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/source/card.ui')
class SourceCard(Gtk.Box):
    __gtype_name__ = "KaoriSourceCard"

    model = GObject.Property(type=models.Source)

    def __init__(self, model=None):
        super().__init__()
        self.model = model

    @Gtk.Template.Callback()
    def get_subtitle(self, obj, is_nsfw):
        if is_nsfw:
            return "18+"
        return "Everyone"
