from gi.repository import Gdk, Gtk

from .base import LAST_PAGE

CTRL_KEYS = (Gdk.KEY_Control_L, Gdk.KEY_Control_R)
FULLSCREEN_KEYS = (Gdk.KEY_f, Gdk.KEY_F)
RETRY_KEYS = (Gdk.KEY_r, Gdk.KEY_R)


class ReaderKeys:
    def __init__(self, page):
        self.page = page
        self.root = None
        self.controller = None
        self.held_ctrl_keys = set()

    def attach(self, root):
        self.detach()
        controller = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self.on_key_pressed)
        controller.connect("key-released", self.on_key_released)
        root.add_controller(controller)
        self.root = root
        self.controller = controller

    def detach(self):
        if self.root is not None and self.controller is not None:
            self.root.remove_controller(self.controller)
        self.root = None
        self.controller = None

    def release_keys(self):
        self.held_ctrl_keys.clear()

    def is_active(self):
        page = self.page
        root = page.get_root()
        if root is None or not page.get_mapped():
            return False
        if root.get_visible_dialog() is not None:
            return False
        focus = root.get_focus()
        if focus is None or focus is page:
            return True
        return focus.is_ancestor(page) and not isinstance(focus, Gtk.Editable)

    def scroll_direction(self, keyval):
        page = self.page
        horizontal = page.webtoon.orientation == Gtk.Orientation.HORIZONTAL
        keys = (Gdk.KEY_Left, Gdk.KEY_Right) if horizontal else (Gdk.KEY_Up, Gdk.KEY_Down)
        if keyval not in keys:
            return 0
        forward = keyval in (Gdk.KEY_Down, Gdk.KEY_Right)
        if horizontal and page.direction == Gtk.TextDirection.RTL:
            forward = not forward
        return 1 if forward else -1

    def on_key_pressed(self, controller, keyval, keycode, state):
        if not self.is_active():
            return False

        page = self.page
        reader = page.active_reader
        rtl = page.direction == Gtk.TextDirection.RTL

        if keyval in CTRL_KEYS:
            self.held_ctrl_keys.add(keyval)
            return False

        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK) or bool(self.held_ctrl_keys)

        if keyval == Gdk.KEY_Escape:
            page.go_back()
            return True

        if keyval == Gdk.KEY_F11 or (keyval in FULLSCREEN_KEYS and not ctrl):
            page.toggle_fullscreen()
            return True

        if ctrl and keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            reader.zoom_in()
            return True
        if ctrl and keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            reader.zoom_out()
            return True
        if ctrl and keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            reader.reset_zoom()
            return True

        if ctrl and keyval in (Gdk.KEY_Right, Gdk.KEY_Left):
            forward = (keyval == Gdk.KEY_Right) != rtl
            page.change_chapter(1 if forward else -1)
            return True
        if keyval == Gdk.KEY_period:
            page.change_chapter(1)
            return True
        if keyval == Gdk.KEY_comma:
            page.change_chapter(-1)
            return True

        if keyval == Gdk.KEY_Home:
            page.webtoon.scroller.stop_all()
            reader.position = 0
            return True
        if keyval == Gdk.KEY_End:
            page.webtoon.scroller.stop_all()
            reader.position = LAST_PAGE
            return True

        if keyval in RETRY_KEYS and not ctrl:
            reader.retry_failed()
            return True

        if reader is page.webtoon:
            return self.on_webtoon_key_pressed(keyval)

        if keyval in (Gdk.KEY_Down, Gdk.KEY_space, Gdk.KEY_Page_Down):
            reader.next_page()
            return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Page_Up, Gdk.KEY_BackSpace):
            reader.previous_page()
            return True

        if keyval in (Gdk.KEY_Right, Gdk.KEY_Left):
            forward = (keyval == Gdk.KEY_Right) != rtl
            if forward:
                reader.next_page()
            else:
                reader.previous_page()
            return True

        return False

    def on_webtoon_key_pressed(self, keyval):
        scroller = self.page.webtoon.scroller
        if keyval == Gdk.KEY_Page_Down:
            scroller.scroll_page(1)
        elif keyval == Gdk.KEY_Page_Up:
            scroller.scroll_page(-1)
        elif direction := self.scroll_direction(keyval):
            scroller.start_keys(direction)
        return True

    def on_key_released(self, controller, keyval, keycode, state):
        if keyval in CTRL_KEYS:
            self.held_ctrl_keys.discard(keyval)
            return
        if not self.is_active():
            return
        scroller = self.page.webtoon.scroller
        if self.scroll_direction(keyval) == scroller.key_direction:
            scroller.stop_keys()
