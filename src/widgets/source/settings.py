import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk


def escaped(text):
    return GLib.markup_escape_text(text or "")


class SourceSettingsDialog(Adw.PreferencesDialog):
    __gtype_name__ = "KaoriSourceSettingsDialog"

    def __init__(self, source):
        super().__init__(title=_("Source Settings"))
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.source = source
        self.page = None
        asyncio.create_task(self.load())

    async def load(self):
        try:
            preferences = await self.suwayomi.getSourcePreferences(self.source.id)
        except Exception as error:
            print("Loading source settings failed:", error)
            self.add_toast(Adw.Toast(title=_("Couldn't load the settings")))
            return
        self.show_preferences(preferences)

    def show_preferences(self, preferences):
        if self.page:
            self.remove(self.page)
        self.page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title=escaped(self.source.name))
        self.page.add(group)
        for preference in preferences:
            if preference["visible"]:
                row = self.make_row(preference)
                row.set_sensitive(preference["enabled"])
                group.add(row)
        self.add(self.page)

    def make_row(self, preference):
        kind = preference["type"]
        title = escaped(preference["title"])
        summary = escaped(preference["summary"])

        if kind in ("SwitchPreference", "CheckBoxPreference"):
            row = Adw.SwitchRow(title=title, subtitle=summary, active=bool(preference["value"]))
            row.connect("notify::active", lambda row, pspec: self.save(preference, row.get_active()))
            return row

        if kind == "EditTextPreference":
            row = Adw.EntryRow(title=title, text=preference["value"] or "", show_apply_button=True)
            row.connect("apply", lambda row: self.save(preference, row.get_text()))
            return row

        if kind == "ListPreference":
            row = Adw.ComboRow(title=title, subtitle=summary, model=Gtk.StringList.new(preference["entries"]))
            if preference["value"] in preference["entry_values"]:
                row.set_selected(preference["entry_values"].index(preference["value"]))
            row.connect("notify::selected", lambda row, pspec: self.save(
                preference, preference["entry_values"][row.get_selected()]))
            return row

        if kind == "MultiSelectListPreference":
            row = Adw.ExpanderRow(title=title, subtitle=summary)
            chosen = set(preference["value"] or [])
            for label, value in zip(preference["entries"], preference["entry_values"]):
                option = Adw.SwitchRow(title=escaped(label), active=value in chosen)
                option.connect("notify::active", self.on_option_toggled, preference, chosen, value)
                row.add_row(option)
            return row

        return Adw.ActionRow(title=title, subtitle=summary)

    def on_option_toggled(self, option, pspec, preference, chosen, value):
        if option.get_active():
            chosen.add(value)
        else:
            chosen.discard(value)
        self.save(preference, [item for item in preference["entry_values"] if item in chosen])

    def save(self, preference, value):
        asyncio.create_task(self.save_value(preference, value))

    async def save_value(self, preference, value):
        try:
            await self.suwayomi.setSourcePreference(self.source.id, preference, value)
        except Exception as error:
            print("Saving the source setting failed:", error)
            self.add_toast(Adw.Toast(title=_("Couldn't save the setting")))
