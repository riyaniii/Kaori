from gi.repository import Gdk, Gtk


def find_scrolled(widget):
    child = widget.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.ScrolledWindow):
            return child
        found = find_scrolled(child)
        if found is not None:
            return found
        child = child.get_next_sibling()
    return None


def sync_store(store, items: list):
    """
    Updates a ListStore to hold items, only touching the range that changed.
    Rows outside that range keep their widgets, so the scroll position stays.
    """
    old = list(store)
    if old == items:
        return

    start = 0
    while start < len(old) and start < len(items) and old[start] is items[start]:
        start += 1

    old_end = len(old)
    new_end = len(items)
    while old_end > start and new_end > start and old[old_end - 1] is items[new_end - 1]:
        old_end -= 1
        new_end -= 1

    store.splice(start, old_end - start, items[start:new_end])


class TopPin:
    """
    Keeps a scrolled window at the very top (section header included) until the
    user scrolls, drags or presses a key.

    A list view focuses its first row when it first appears and scrolls so that
    row is visible, which leaves the first section header cut off. That scroll
    is an ordinary value change, so the pin watches the value and puts it back.
    """

    def __init__(self, scrolled: Gtk.ScrolledWindow):
        self.adjustment = scrolled.get_vadjustment()
        self.started = False
        self.pinned = False
        self.resetting = False

        self.adjustment.connect("value-changed", self.on_moved)
        self.adjustment.connect("changed", self.on_moved)

        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES,
            propagation_phase=Gtk.PropagationPhase.CAPTURE,
        )
        scroll.connect("scroll", self.on_user_input)
        scrolled.add_controller(scroll)

        drag = Gtk.GestureDrag(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        drag.connect("drag-begin", self.on_user_input)
        scrolled.add_controller(drag)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_user_input)
        scrolled.add_controller(keys)

    def content_ready(self):
        if self.started:
            return
        self.started = True
        self.pinned = True
        self.scroll_to_top()

    def scroll_to_top(self):
        if self.resetting or self.adjustment.get_value() == 0:
            return
        self.resetting = True
        try:
            self.adjustment.set_value(0)
        finally:
            self.resetting = False

    def on_moved(self, adjustment):
        if self.pinned:
            self.scroll_to_top()

    def on_user_input(self, *args):
        self.pinned = False
        return Gdk.EVENT_PROPAGATE
