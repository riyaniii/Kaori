from gi.repository import Gtk


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

