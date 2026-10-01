from gi.repository import Adw, GObject, Gtk

# Position in each combo row's model
ORIENTATIONS = [Gtk.Orientation.VERTICAL, Gtk.Orientation.HORIZONTAL]
DIRECTIONS = [Gtk.TextDirection.LTR, Gtk.TextDirection.RTL]


@Gtk.Template(resource_path='/com/rini/kaghez/reader/dialog.ui')
class SettingsDialog(Adw.Dialog):
    __gtype_name__ = "KaghezSettingsDialog"

    stack = GObject.Property(type=Gtk.Widget)

    orientation_row = Gtk.Template.Child()
    direction_row = Gtk.Template.Child()

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.webtoon = stack.get_child_by_name("webtoon")

        self.updating = True
        self.orientation_row.set_selected(ORIENTATIONS.index(self.webtoon.orientation))
        self.direction_row.set_selected(DIRECTIONS.index(self.webtoon.direction))
        self.updating = False

    @Gtk.Template.Callback()
    def is_webtoon(self, obj, visible_child_name):
        return visible_child_name == "webtoon"

    @Gtk.Template.Callback()
    def on_orientation_changed(self, row, pspec):
        if not self.updating:
            self.webtoon.orientation = ORIENTATIONS[row.get_selected()]

    @Gtk.Template.Callback()
    def on_direction_changed(self, row, pspec):
        if not self.updating:
            self.webtoon.direction = DIRECTIONS[row.get_selected()]
