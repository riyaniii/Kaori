from gi.repository import Gtk, Adw, GObject, Gio

TRI_STATES = ["IGNORE", "INCLUDE", "EXCLUDE"]


class FilterEntry(GObject.Object):
    __gtype_name__ = "KaoriFilterEntry"

    def __init__(self, node, path):
        super().__init__()
        self.node = node
        self.path = path


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/source/filter.ui')
class SourceFilter(Adw.Dialog):
    __gtype_name__ = "KaoriSourceFilter"

    filter_stack = Gtk.Template.Child()
    filter_page = Gtk.Template.Child()

    @GObject.Signal(arg_types=(object,))
    def applied(self, changes):
        pass

    def __init__(self):
        super().__init__()
        self.filters = []
        self.changes = {}
        self.groups = []
        self.tri_states = {}
        self.tri_buttons = {}
        self.sort_rows = {}
        self.updating = False

    def set_filters(self, filters):
        self.filters = filters
        self.rebuild()

    def rebuild(self):
        for group in self.groups:
            self.filter_page.remove(group)
        self.groups = []
        self.changes = {}
        self.tri_states = {}
        self.tri_buttons = {}
        self.sort_rows = {}

        if not self.filters:
            self.filter_stack.set_visible_child_name("empty")
            return

        title = None
        pending = []

        def flush():
            nonlocal pending
            if pending:
                store = Gio.ListStore.new(item_type=FilterEntry)
                store.splice(0, 0, pending)
                group = Adw.PreferencesGroup(title=title or "")
                group.bind_model(store, self.create_row)
                self.filter_page.add(group)
                self.groups.append(group)
            pending = []

        for position, node in enumerate(self.filters):
            if node["type"] == "HeaderFilter":
                flush()
                title = node["name"]
            elif node["type"] == "SeparatorFilter":
                flush()
                title = None
            else:
                pending.append(FilterEntry(node, (position,)))
        flush()

        self.filter_stack.set_visible_child_name("filters")

    def create_row(self, item):
        kind = item.node["type"]
        if kind == "CheckBoxFilter":
            return self.make_check_row(item)
        if kind == "TriStateFilter":
            return self.make_tri_row(item)
        if kind == "SelectFilter":
            return self.make_select_row(item)
        if kind == "TextFilter":
            return self.make_text_row(item)
        if kind == "SortFilter":
            return self.make_sort_row(item)
        if kind == "GroupFilter":
            return self.make_group_row(item)
        return Gtk.Label()  

    def make_check_row(self, item):
        row = Adw.SwitchRow(title=item.node["name"], active=bool(item.node["default"]))
        row.connect("notify::active", self.on_check_changed, item.path)
        return row

    def make_select_row(self, item):
        row = Adw.ComboRow(
            title=item.node["name"],
            model=Gtk.StringList.new(item.node["values"]),
            selected=item.node["default"] or 0,
        )
        row.connect("notify::selected", self.on_select_changed, item.path)
        return row

    def make_text_row(self, item):
        row = Adw.EntryRow(title=item.node["name"], text=item.node["default"] or "")
        row.connect("changed", self.on_text_changed, item.path)
        return row

    def make_sort_row(self, item):
        default = item.node["default"] or {}
        index = default.get("index")

        row = Adw.ComboRow(title=item.node["name"], model=Gtk.StringList.new(item.node["values"]))
        row.set_selected(Gtk.INVALID_LIST_POSITION if index is None else index)

        button = Gtk.ToggleButton(active=default.get("ascending", True), valign=Gtk.Align.CENTER)
        button.add_css_class("flat")
        self.update_sort_icon(button)
        row.add_suffix(button)

        self.sort_rows[item.path] = (row, button)
        row.connect("notify::selected", self.on_sort_selected, item.path)
        button.connect("toggled", self.on_sort_toggled, item.path)
        return row

    def make_tri_row(self, item):
        path = item.path
        self.tri_states[path] = item.node["default"] or "IGNORE"

        button = Gtk.CheckButton(valign=Gtk.Align.CENTER)
        self.tri_buttons[path] = button
        self.update_tri_button(path)
        button.connect("toggled", self.on_tri_toggled, path)

        row = Adw.ActionRow(title=item.node["name"])
        row.add_prefix(button)
        row.set_activatable_widget(button)
        return row

    def make_group_row(self, item):
        expander = Adw.ExpanderRow(title=item.node["name"])
        populated = False

        def on_expanded(row, pspec):
            nonlocal populated
            if populated or not row.get_expanded():
                return
            populated = True
            self.populate_group(row, item)

        expander.connect("notify::expanded", on_expanded)
        return expander

    def populate_group(self, expander, item):
        for position, child in enumerate(item.node["filters"]):
            child_path = item.path + (position,)
            if child["type"] == "SeparatorFilter":
                continue
            if child["type"] == "HeaderFilter":
                header = Adw.ActionRow(title=child["name"])
                header.add_css_class("dimmed")
                expander.add_row(header)
                continue
            if child["type"] == "GroupFilter":
                header = Adw.ActionRow(title=child["name"])
                header.add_css_class("dimmed")
                expander.add_row(header)
                self.populate_group(expander, FilterEntry(child, child_path))
                continue
            expander.add_row(self.create_row(FilterEntry(child, child_path)))

    def set_change(self, path, change):
        self.changes[path] = change

    def on_check_changed(self, row, pspec, path):
        self.set_change(path, {"checkBoxState": row.get_active()})

    def on_tri_toggled(self, button, path):
        if self.updating:
            return
        current = TRI_STATES.index(self.tri_states[path])
        state = TRI_STATES[(current + 1) % len(TRI_STATES)]
        self.tri_states[path] = state
        self.update_tri_button(path)
        self.set_change(path, {"triState": state})

    def update_tri_button(self, path):
        button = self.tri_buttons[path]
        state = self.tri_states[path]
        self.updating = True
        button.set_inconsistent(state == "EXCLUDE")
        button.set_active(state == "INCLUDE")
        self.updating = False

    def on_select_changed(self, row, pspec, path):
        self.set_change(path, {"selectState": row.get_selected()})

    def on_text_changed(self, row, path):
        self.set_change(path, {"textState": row.get_text()})

    def on_sort_selected(self, row, pspec, path):
        self.update_sort(path)

    def on_sort_toggled(self, button, path):
        self.update_sort_icon(button)
        self.update_sort(path)

    def update_sort_icon(self, button):
        if button.get_active():
            button.set_icon_name("view-sort-ascending-symbolic")
        else:
            button.set_icon_name("view-sort-descending-symbolic")

    def update_sort(self, path):
        row, button = self.sort_rows[path]
        index = row.get_selected()
        if index == Gtk.INVALID_LIST_POSITION:
            return
        self.set_change(path, {"sortState": {"index": index, "ascending": button.get_active()}})

    def make_change(self, path, change):
        node = {"position": path[-1], **change}
        for position in reversed(path[:-1]):
            node = {"position": position, "groupChange": node}
        return node

    @Gtk.Template.Callback()
    def on_reset_clicked(self, *_):
        self.rebuild()

    @Gtk.Template.Callback()
    def on_apply_clicked(self, *_):
        changes = [self.make_change(path, change) for path, change in self.changes.items()]
        self.emit("applied", changes)
        self.close()
