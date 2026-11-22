import asyncio
from gettext import gettext as _, ngettext
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from .card import ExtensionCard


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/extension/extensions.ui')
class ExtensionsPage(Adw.NavigationPage):
    __gtype_name__ = "KaoriExtensionsPage"

    update_banner = Gtk.Template.Child()

    search_text = GObject.Property(type=str)
    extensions = GObject.Property(type=Gio.ListStore)

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.extensions = self.suwayomi.extensions
        self.extensions.connect("items-changed", lambda *args: self.update_banner_text())
        asyncio.create_task(self.suwayomi.refreshExtensions())

    def update_banner_text(self):
        count = sum(1 for extension in self.extensions if extension.has_update)
        message = ngettext("{} extension can be updated", "{} extensions can be updated", count)
        self.update_banner.set_title(message.format(count))
        self.update_banner.set_revealed(count > 0)

    @Gtk.Template.Callback()
    def on_update_all_clicked(self, banner):
        asyncio.create_task(self.update_all())

    async def update_all(self):
        self.update_banner.set_revealed(False)
        try:
            await self.suwayomi.updateAllExtensions()
        except Exception as error:
            print("Updating extensions failed:", error)
            self.activate_action("app.show_toast", GLib.Variant("s", _("Couldn't update the extensions")))
        self.update_banner_text()

    @Gtk.Template.Callback()
    def get_page(self, obj, count):
        return "extensions" if count > 0 else "greeter"

    @Gtk.Template.Callback()
    def on_setup(self, factory, list_item):
        list_item.set_activatable(True)
        list_item.set_child(ExtensionCard())

    @Gtk.Template.Callback()
    def on_bind(self, factory, list_item):
        card = list_item.get_child()
        card.model = list_item.get_item()
        card.icon_task = asyncio.create_task(self.suwayomi.loadIcon(card.model))

    @Gtk.Template.Callback()
    def on_unbind(self, factory, list_item):
        card = list_item.get_child()
        card.icon_task.cancel()
        card.model.paintable = None
        card.model = None

    @Gtk.Template.Callback()
    def on_header_setup(self, factory, header):
        header.set_child(Gtk.Label(
            xalign=0, css_classes=["title-4"],
            margin_top=18, margin_bottom=6, margin_start=6,
        ))

    @Gtk.Template.Callback()
    def on_header_bind(self, factory, header):
        header.get_child().set_label(self.suwayomi.languageTitle(header.get_item().lang))

    @Gtk.Template.Callback()
    def on_activate(self, listview, position):
        item = listview.get_model().get_item(position)
        listview.activate_action("app.show_extension", GLib.Variant("s", item.pkg_name))
