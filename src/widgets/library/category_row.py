from gi.repository import GObject, Gtk


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/library/category_row.ui')
class CategoryRow(Gtk.Box):
    __gtype_name__ = 'KaoriCategoryRow'

    name_label = Gtk.Template.Child()
    count_label = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.bindings = []

    def bind_category(self, category):
        self.unbind_category()
        self.bindings = [
            category.bind_property(
                "name", self.name_label, "label",
                GObject.BindingFlags.SYNC_CREATE,
            ),
            category.bind_property(
                "manga-count", self.count_label, "label",
                GObject.BindingFlags.SYNC_CREATE,
                lambda binding, value: str(value),
            ),
        ]

    def unbind_category(self):
        for binding in self.bindings:
            binding.unbind()
        self.bindings = []
