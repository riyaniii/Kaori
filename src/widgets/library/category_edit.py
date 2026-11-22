import asyncio

from gi.repository import Adw, Gio, Gtk

from ...integrations.suwayomi import DEFAULT_CATEGORY_ID


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/library/category_edit.ui')
class CategoryEditDialog(Adw.Dialog):
    __gtype_name__ = "KaoriCategoryEditDialog"

    stack = Gtk.Template.Child()
    group = Gtk.Template.Child()

    def __init__(self, manga, on_manage):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.manga = manga
        self.on_manage = on_manage
        self.initial = self.suwayomi.mangaCategoryIds(manga.id)
        self.selected = set(self.initial)

        found = False
        for category in self.suwayomi.categories:
            if category.id == DEFAULT_CATEGORY_ID:
                continue
            found = True
            row = Adw.SwitchRow(title=category.name, active=category.id in self.selected)
            row.connect("notify::active", self.on_toggled, category.id)
            self.group.add(row)

        self.stack.set_visible_child_name("list" if found else "empty")

    def on_toggled(self, row, pspec, category_id):
        if row.get_active():
            self.selected.add(category_id)
        else:
            self.selected.discard(category_id)

    @Gtk.Template.Callback()
    def on_save_clicked(self, button):
        add = sorted(self.selected - self.initial)
        remove = sorted(self.initial - self.selected)
        self.close()
        if add or remove:
            asyncio.create_task(self.suwayomi.setMangaCategories(self.manga.id, add, remove))

    @Gtk.Template.Callback()
    def on_manage_clicked(self, button):
        self.close()
        self.on_manage()
