import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gio, GObject, Gtk

from ...integrations.suwayomi import DEFAULT_CATEGORY_ID, watch


def star_icon(binding, is_default):
    if is_default:
        return "starred-symbolic"
    return "non-starred-symbolic"


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/library/category_manager.ui')
class CategoryManagerDialog(Adw.Dialog):
    __gtype_name__ = "KaoriCategoryManagerDialog"

    categories_group = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.rows = []
        self.rebuild()
        watch(self, self.suwayomi.categories, self.rebuild)

    def user_categories(self):
        categories = []
        for category in self.suwayomi.categories:
            if category.id != DEFAULT_CATEGORY_ID:
                categories.append(category)
        return categories

    def rebuild(self):
        for row in self.rows:
            self.categories_group.remove(row)
        self.rows = []

        for category in self.user_categories():
            self.add_row(category)

    def make_button(self, icon_name, tooltip):
        return Gtk.Button(
            icon_name=icon_name,
            valign=Gtk.Align.CENTER,
            css_classes=["flat"],
            tooltip_text=tooltip,
        )

    def add_row(self, category):
        row = Adw.EntryRow(title=_("Name"), text=category.name, show_apply_button=True)
        row.connect("apply", self.on_rename_applied, category)

        handle = Gtk.Image(icon_name="list-drag-handle-symbolic", valign=Gtk.Align.CENTER)
        handle.set_cursor_from_name("grab")
        row.add_prefix(handle)

        drag_source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag_source.connect("prepare", self.on_drag_prepare, category)
        drag_source.connect("drag-begin", self.on_drag_begin, row)
        handle.add_controller(drag_source)

        drop_target = Gtk.DropTarget.new(GObject.TYPE_INT, Gdk.DragAction.MOVE)
        drop_target.connect("enter", self.on_drop_enter, row)
        drop_target.connect("leave", self.on_drop_leave, row)
        drop_target.connect("drop", self.on_drop, row, category)
        row.add_controller(drop_target)

        default_button = self.make_button("non-starred-symbolic", _("Use as default category"))
        category.bind_property(
            "is-default", default_button, "icon-name",
            GObject.BindingFlags.SYNC_CREATE, star_icon,
        )
        default_button.connect("clicked", self.on_default_clicked, category)

        delete_button = self.make_button("user-trash-symbolic", _("Delete category"))
        delete_button.connect("clicked", self.on_delete_clicked, category)

        row.add_suffix(default_button)
        row.add_suffix(delete_button)

        self.categories_group.add(row)
        self.rows.append(row)

    def on_drag_prepare(self, source, x, y, category):
        value = GObject.Value(GObject.TYPE_INT, category.id)
        return Gdk.ContentProvider.new_for_value(value)

    def on_drag_begin(self, source, drag, row):
        source.set_icon(Gtk.WidgetPaintable.new(row), 0, 0)

    def on_drop_enter(self, target, x, y, row):
        row.add_css_class("drop-target")
        return Gdk.DragAction.MOVE

    def on_drop_leave(self, target, row):
        row.remove_css_class("drop-target")

    def on_drop(self, target, value, x, y, row, category):
        row.remove_css_class("drop-target")
        if value == category.id:
            return False
        asyncio.create_task(self.suwayomi.moveCategory(value, category.order))
        return True

    def on_rename_applied(self, row, category):
        name = row.get_text().strip()
        if name and name != category.name:
            asyncio.create_task(self.suwayomi.renameCategory(category.id, name))

    def on_default_clicked(self, button, category):
        asyncio.create_task(self.suwayomi.setCategoryDefault(category.id, not category.is_default))

    def on_delete_clicked(self, button, category):
        button.set_sensitive(False)
        asyncio.create_task(self.suwayomi.deleteCategory(category.id))

    @Gtk.Template.Callback()
    def on_new_applied(self, row):
        name = row.get_text().strip()
        if name:
            row.set_text("")
            asyncio.create_task(self.suwayomi.createCategory(name))
