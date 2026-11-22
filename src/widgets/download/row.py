from gi.repository import Gtk, Gdk, GObject

from ...integrations import models


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/download/row.ui')
class DownloadRow(Gtk.Box):
    __gtype_name__ = "KaoriDownloadRow"

    model = GObject.Property(type=models.Download)

    handle = Gtk.Template.Child()

    @GObject.Signal(arg_types=(int, int))
    def reorder_requested(self, dragged_chapter_id, target_chapter_id):
        pass

    @GObject.Signal(arg_types=(int,))
    def remove_requested(self, chapter_id):
        pass

    @GObject.Signal(arg_types=(int,))
    def retry_requested(self, chapter_id):
        pass

    def __init__(self, model=None):
        super().__init__()
        if model is not None:
            self.model = model

        self.handle.set_cursor_from_name("grab")

        drag_source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag_source.connect("prepare", self.on_drag_prepare)
        drag_source.connect("drag-begin", self.on_drag_begin)
        self.handle.add_controller(drag_source)

        drop_target = Gtk.DropTarget.new(GObject.TYPE_INT, Gdk.DragAction.MOVE)
        drop_target.connect("enter", self.on_drop_enter)
        drop_target.connect("leave", self.on_drop_leave)
        drop_target.connect("drop", self.on_drop)
        self.add_controller(drop_target)

    def on_drag_prepare(self, source, x, y):
        if self.model is None:
            return None
        value = GObject.Value(GObject.TYPE_INT, self.model.chapter_id)
        return Gdk.ContentProvider.new_for_value(value)

    def on_drag_begin(self, source, drag):
        source.set_icon(Gtk.WidgetPaintable.new(self), 0, 0)

    def on_drop_enter(self, target, x, y):
        self.add_css_class("drop-target")
        return Gdk.DragAction.MOVE

    def on_drop_leave(self, target):
        self.remove_css_class("drop-target")

    def on_drop(self, target, value, x, y):
        self.remove_css_class("drop-target")
        if self.model is None or value == self.model.chapter_id:
            return False
        self.emit("reorder-requested", value, self.model.chapter_id)
        return True

    @Gtk.Template.Callback()
    def is_error(self, obj, state):
        return (state or "").upper() == "ERROR"

    @Gtk.Template.Callback()
    def on_retry_clicked(self, *args):
        if self.model:
            self.emit("retry-requested", self.model.chapter_id)

    @Gtk.Template.Callback()
    def on_remove_clicked(self, *args):
        if self.model:
            self.emit("remove-requested", self.model.chapter_id)
