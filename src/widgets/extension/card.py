import asyncio

from gi.repository import Gtk, Gio, GObject

from ...integrations import models

@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/extension/card.ui')
class ExtensionCard(Gtk.Box):
    __gtype_name__ = "KaoriExtensionCard"

    model = GObject.Property(type=models.Extension)

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi

        self.actions = Gio.SimpleActionGroup()
        self.insert_action_group("extension", self.actions)

        self.add_extension_action("apply", self.on_apply)

    def add_extension_action(self, name, callback, param_type=None):
        action = Gio.SimpleAction.new(name, param_type)
        action.connect("activate", callback)
        self.actions.add_action(action)

    def on_apply(self, *_):
        asyncio.create_task(self.apply())

    async def apply(self):
        model = self.model

        if model.has_update:
            await self.suwayomi.updateExtension(model.pkg_name)
        elif model.is_installed:
            await self.suwayomi.uninstallExtension(model.pkg_name)
        else:
            await self.suwayomi.installExtension(model.pkg_name)

    @Gtk.Template.Callback()
    def get_subtitle(self, obj, lang, version_name, is_nsfw):
        parts = []
        if lang:
            parts.append(self.suwayomi.languageTitle(lang))
        if version_name:
            parts.append("v" + version_name)
        if is_nsfw:
            parts.append("18+")
        else:
            parts.append("Everyone")
        return " · ".join(parts)

    @Gtk.Template.Callback()
    def get_action_button_tooltip(self, obj, is_installed, has_update):
        if has_update:
            return "Update"
        elif is_installed:
            return "Uninstall"
        else:
            return "Install"

    @Gtk.Template.Callback()
    def get_action_button_icon_name(self, obj, is_installed, has_update):
        if has_update:
            return "up-symbolic"
        elif is_installed:
            return "list-remove-symbolic"
        else:
            return "list-add-symbolic"

    @Gtk.Template.Callback()
    def get_not(self, obj, value):
        return not value
