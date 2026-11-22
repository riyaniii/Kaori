from gi.repository import Gtk, GObject

from ...integrations import models
from ..common.manga_menu import MangaMenu


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/manga/card.ui')
class MangaCard(Gtk.Box):
    __gtype_name__ = "KaoriMangaCard"

    model = GObject.Property(type=models.Manga)
    options = GObject.Property(type=models.CardOptions)
    show_title = GObject.Property(type=bool, default=True)

    def __init__(self, model=None, **kwargs):
        super().__init__(**kwargs)
        self.options = models.CardOptions(show_unread_badge=False)
        if model is not None:
            self.model = model
        self.manga_menu = MangaMenu(self, lambda: self.model)

    def do_dispose(self):
        self.manga_menu.close()
        Gtk.Box.do_dispose(self)

    @Gtk.Template.Callback()
    def title_visible(self, obj, show_title, mode):
        return show_title and mode != "compact"

    @Gtk.Template.Callback()
    def overlay_title_visible(self, obj, show_title, mode):
        return show_title and mode == "compact"

    @Gtk.Template.Callback()
    def badge_visible(self, obj, enabled, count):
        return enabled and count > 0

    @Gtk.Template.Callback()
    def number_text(self, obj, count):
        return str(count)
