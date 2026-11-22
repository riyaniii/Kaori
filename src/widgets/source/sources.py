import asyncio
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from .card import SourceCard


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/source/sources.ui')
class SourcesPage(Adw.NavigationPage):
    __gtype_name__ = "KaoriSourcesPage"

    search_text = GObject.Property(type=str)
    sources = GObject.Property(type=Gio.ListStore)

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.sources = self.suwayomi.sources
        asyncio.create_task(self.suwayomi.refreshSources())

    @Gtk.Template.Callback()
    def on_shown(self, *_):
        asyncio.create_task(self.suwayomi.refreshSources())

    @Gtk.Template.Callback()
    def get_page(self, obj, count):
        return "sources" if count > 0 else "greeter"

    @Gtk.Template.Callback()
    def on_setup(self, factory, list_item):
        list_item.set_child(SourceCard())

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
        listview.activate_action("app.show_source", GLib.Variant("s", item.id))
