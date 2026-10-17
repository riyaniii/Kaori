from gi.repository import Gtk, Gio, GObject
from ...integrations.suwayomi import watch


class CategoryBar(Gtk.ScrolledWindow):
    __gtype_name__ = 'KaoriCategoryBar'
    __gsignals__ = {'selected': (GObject.SignalFlags.RUN_FIRST, None, (int,))}

    def __init__(self):
        super().__init__(
            vscrollbar_policy=Gtk.PolicyType.NEVER,
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        self.box = Gtk.Box(spacing=6, margin_start=12, margin_end=12, margin_top=6, margin_bottom=6)
        self.set_child(self.box)

        self.suwayomi = Gio.Application.get_default().suwayomi
        self.selected_id = -1

        self.rebuild()
        watch(self, self.suwayomi.categories, self.rebuild)

    def rebuild(self):
        while child := self.box.get_first_child():
            self.box.remove(child)

        categories = list(self.suwayomi.categories)
        ids = [category.id for category in categories]
        self.set_visible(len(categories) > 1)

        if len(categories) > 1:
            if self.selected_id in ids:
                target = self.selected_id
            else:
                target = ids[0]
        else:
            target = -1

        first = None
        for category in categories:
            button = Gtk.ToggleButton(label=category.name)
            button.add_css_class("flat")
            if first is None:
                first = button
            else:
                button.set_group(first)
            button.set_active(category.id == target)
            button.connect("toggled", self.on_toggled, category.id)
            self.box.append(button)

        self.selected_id = target
        self.emit("selected", target)

    def on_toggled(self, button, category_id):
        if button.get_active():
            self.selected_id = category_id
            self.emit("selected", category_id)
