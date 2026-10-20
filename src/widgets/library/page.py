import asyncio
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ..manga import MangaCard
from ..containers import MangaGrid
from ...integrations import models
from ...integrations.suwayomi import watch

DISPLAY_BINDINGS = (
    ("library-display-mode", "display-mode"),
    ("library-show-unread-badge", "show-unread-badge"),
    ("library-show-download-badge", "show-download-badge"),
)


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/library/page.ui')
class LibraryPage(Adw.NavigationPage):
    __gtype_name__ = "KaoriLibraryPage"

    manga_grid = Gtk.Template.Child()
    category_button = Gtk.Template.Child()
    options_dialog = Gtk.Template.Child()
    source_group = Gtk.Template.Child()

    library_size = GObject.Property(type=int, default=0)

    def __init__(self):
        super().__init__()
        app = Gio.Application.get_default()
        self.suwayomi = app.suwayomi

        library = self.suwayomi.library
        self.manga_grid.bind_store(library)
        library.bind_property("n-items", self, "library_size", GObject.BindingFlags.SYNC_CREATE)

        self.options = models.LibraryOptions()
        for settings_key, option_name in DISPLAY_BINDINGS:
            app.settings.bind(settings_key, self.options, option_name,
                              Gio.SettingsBindFlags.GET)
        self.manga_grid.use_options(self.options)

        actions = self.options.make_actions()
        self.options_dialog.insert_action_group("library", actions)
        self.source_rows = []

        self.manga_grid.set_category(self.suwayomi.selected_category)
        watch(self, self.suwayomi, self.on_category_changed, "notify::selected-category")
        self.update_category_button()
        watch(self, self.suwayomi.categories, self.update_category_button)

        asyncio.create_task(self.suwayomi.refreshLibrary())

    def on_category_changed(self):
        self.manga_grid.set_category(self.suwayomi.selected_category)

    def update_category_button(self):
        self.category_button.set_visible(self.suwayomi.categories.get_n_items() > 1)

    def add_source(self, label, source_id, first):
        check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
        check.set_action_target_value(GLib.Variant.new_string(source_id))
        check.set_action_name("library.source-id")
        if first is not None:
            check.set_group(first)

        row = Adw.ActionRow(title=label, activatable_widget=check)
        row.add_prefix(check)
        self.source_group.add(row)
        self.source_rows.append(row)
        return check

    def refresh_sources(self):
        for row in self.source_rows:
            self.source_group.remove(row)
        self.source_rows = []

        used = set(manga.source_id for manga in self.suwayomi.library)

        names = {}
        for source in self.suwayomi.all_sources:
            if source.lang in ("", "all", "localsourcelang"):
                names[source.id] = source.name
            else:
                names[source.id] = f"{source.name} ({source.lang})"

        labeled = []
        for source_id in used:
            if source_id:
                labeled.append((names.get(source_id, source_id), source_id))

        if self.options.source_id and self.options.source_id not in used:
            self.options.source_id = ""

        first = self.add_source("All sources", "", None)
        for label, source_id in sorted(labeled):
            self.add_source(label, source_id, first)

    @Gtk.Template.Callback()
    def get_page(self, obj, size):
        return "grid" if size > 0 else "greeter"

    @Gtk.Template.Callback()
    def on_search_changed(self, entry):
        self.manga_grid.set_search_text(entry.get_text())

    @Gtk.Template.Callback()
    def on_options_clicked(self, button):
        self.refresh_sources()
        self.options_dialog.present(self)
