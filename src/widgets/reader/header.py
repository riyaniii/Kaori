from gi.repository import GLib, Gtk

HEADER_HOVER_HEIGHT = 48
HEADER_HIDE_DELAY = 1500


class ReaderHeader:
    def __init__(self, page):
        self.page = page
        self.root = None
        self.handlers = []
        self.pointer_in_zone = True
        self.hide_id = 0

        motion = Gtk.EventControllerMotion(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        motion.connect("enter", self.on_pointer_motion)
        motion.connect("motion", self.on_pointer_motion)
        page.add_controller(motion)

        self.focus = Gtk.EventControllerFocus()
        self.focus.connect("notify::contains-focus", self.update)
        page.header.add_controller(self.focus)

    def attach(self, root):
        self.detach()
        self.root = root
        split_view = root.overlay_split_view
        self.handlers = [
            (root, root.connect("notify::visible-dialog", self.update)),
            (split_view, split_view.connect("notify::show-sidebar", self.update)),
        ]
        self.update()

    def detach(self):
        for obj, handler_id in self.handlers:
            obj.disconnect(handler_id)
        self.handlers = []
        self.root = None

    def on_pointer_motion(self, controller, x, y):
        inside = y <= HEADER_HOVER_HEIGHT
        if inside != self.pointer_in_zone:
            self.pointer_in_zone = inside
            self.update()

    def update(self, *args):
        root = self.root
        if root is None:
            return

        keep_open = (
            self.pointer_in_zone
            or root.get_visible_dialog() is not None
            or root.overlay_split_view.get_show_sidebar()
            or (self.focus.props.contains_focus and root.get_focus_visible())
        )

        revealer = self.page.revealer
        if keep_open:
            self.cancel_hide()
            revealer.set_reveal_child(True)
        elif revealer.get_reveal_child() and not self.hide_id:
            self.hide_id = GLib.timeout_add(HEADER_HIDE_DELAY, self.hide)

    def hide(self):
        self.hide_id = 0
        self.page.revealer.set_reveal_child(False)
        return GLib.SOURCE_REMOVE

    def cancel_hide(self):
        if self.hide_id:
            GLib.source_remove(self.hide_id)
            self.hide_id = 0
