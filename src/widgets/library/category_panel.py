from gi.repository import Adw, Gio, GObject, Gtk

from ...integrations.suwayomi import watch
from .category_edit import CategoryEditDialog
from .category_manager import CategoryManagerDialog
from .category_row import CategoryRow


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/library/category_panel.ui')
class CategoryPanel(Adw.Bin):
    __gtype_name__ = 'KaoriCategoryPanel'
    __gsignals__ = {'activated': (GObject.SignalFlags.RUN_FIRST, None, ())}

    category_list = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi

        self.selection = Gtk.SingleSelection(
            model=self.suwayomi.categories
        )
        self.category_list.set_model(self.selection)
        self.selection.connect("notify::selected", self.on_selected_changed)

        self.sync_selection()
        watch(self, self.suwayomi.categories, self.sync_selection)

    def edit_categories(self, manga):
        CategoryEditDialog(manga, self.manage_categories).present(self)

    def manage_categories(self):
        CategoryManagerDialog().present(self)

    def select(self, category_id):
        if self.suwayomi.selected_category != category_id:
            self.suwayomi.selected_category = category_id

    def sync_selection(self):
        ids = [category.id for category in self.suwayomi.categories]

        if len(ids) > 1:
            current = self.suwayomi.selected_category
            target = current if current in ids else ids[0]
        else:
            target = -1

        if target == -1:
            self.selection.set_selected(Gtk.INVALID_LIST_POSITION)
        else:
            self.selection.set_selected(ids.index(target))

        self.select(target)
        if target == -1:
            self.emit("activated")

    def on_selected_changed(self, selection, pspec):
        category = selection.get_selected_item()
        if category is not None:
            self.select(category.id)

    @Gtk.Template.Callback()
    def on_setup(self, factory, list_item):
        list_item.set_child(CategoryRow())

    @Gtk.Template.Callback()
    def on_bind(self, factory, list_item):
        list_item.get_child().bind_category(list_item.get_item())

    @Gtk.Template.Callback()
    def on_unbind(self, factory, list_item):
        list_item.get_child().unbind_category()

    @Gtk.Template.Callback()
    def on_activate(self, listview, position):
        self.emit("activated")

    @Gtk.Template.Callback()
    def on_manage_clicked(self, button):
        self.manage_categories()
