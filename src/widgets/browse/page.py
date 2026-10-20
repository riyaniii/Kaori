import asyncio
from gi.repository import Adw, Gio, Gtk

from ..source.sources import SourcesPage
from ..extension.extensions import ExtensionsPage

from ...integrations.suwayomi import LOCAL_SOURCE_ID


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/browse/page.ui')
class BrowsePage(Adw.NavigationPage):
    __gtype_name__ = "KaoriBrowsePage"

    sources_page = Gtk.Template.Child()
    extensions_page = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi

    @Gtk.Template.Callback()
    def get_placeholder(self, obj, page_name):
        if page_name == "extensions":
            return "Find an extension"
        return "Find a source"

    @Gtk.Template.Callback()
    def on_search_changed(self, entry):
        text = entry.get_text().strip()
        self.sources_page.search_text = text
        self.extensions_page.search_text = text

    @Gtk.Template.Callback()
    def on_languages_clicked(self, *_):
        langs = {s.lang for s in self.suwayomi.all_sources if s.id != LOCAL_SOURCE_ID}

        group = Adw.PreferencesGroup(description="Only sources in these languages are used")
        for lang in sorted(langs, key=lambda l: (l != "all", l)):
            row = Adw.SwitchRow(
                title=self.suwayomi.languageTitle(lang),
                active=lang in self.suwayomi.languages,
            )
            row.connect("notify::active", self.on_language_toggled, lang)
            group.add(row)

        page = Adw.PreferencesPage()
        page.add(group)
        dialog = Adw.PreferencesDialog(title="Languages")
        dialog.add(page)
        dialog.present(self)

    def on_language_toggled(self, row, pspec, lang):
        languages = [l for l in self.suwayomi.languages if l != lang]
        if row.get_active():
            languages.append(lang)
        asyncio.create_task(self.suwayomi.setBrowseLanguages(languages))
