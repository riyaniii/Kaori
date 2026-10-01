from gi.repository import Gtk

from .base import PagedReader


@Gtk.Template(resource_path='/com/rini/kaghez/reader/single.ui')
class SinglePageReader(PagedReader):
    __gtype_name__ = "KaghezSinglePageReader"

    picture = Gtk.Template.Child()

    @property
    def pictures(self):
        return [self.picture]

    @property
    def content(self):
        return self.picture
