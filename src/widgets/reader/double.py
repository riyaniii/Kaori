from gi.repository import Gtk

from .base import PagedReader


@Gtk.Template(resource_path='/com/rini/kaghez/reader/double.ui')
class DoublePageReader(PagedReader):
    __gtype_name__ = "KaghezDoublePageReader"

    spread = Gtk.Template.Child()
    left_frame = Gtk.Template.Child()
    right_frame = Gtk.Template.Child()
    left_picture = Gtk.Template.Child()
    right_picture = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for widget in (self.spread, self.left_frame, self.right_frame):
            widget.set_direction(Gtk.TextDirection.LTR)
        self.connect("notify::direction", self.on_direction_changed)

    @property
    def pictures(self):
        if self.get_direction() == Gtk.TextDirection.RTL:
            return [self.right_picture, self.left_picture]
        return [self.left_picture, self.right_picture]

    @property
    def content(self):
        return self.spread

    def on_direction_changed(self, reader, pspec):
        if self.store:
            self.show_current()
