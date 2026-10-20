from gi.repository import Gtk, GObject, Gio, GLib
from ..manga import MangaCard
from ...integrations import models

@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/containers/row.ui')
class MangaRow(Gtk.Box):
    __gtype_name__ = 'KaoriMangaRow'

    listview = Gtk.Template.Child()

    title = GObject.Property(type=str, default="")

    def __init__(self, title, **kwargs):
        super().__init__(**kwargs)
        self.title = title

        self.suwayomi = Gio.Application.get_default().suwayomi

        self.store = Gio.ListStore(item_type=models.Manga)

        selection = Gtk.NoSelection(model=self.store)
        self.listview.set_model(selection)
        self.listview.connect('activate', self.on_activate)

        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', self.on_setup)
        factory.connect('bind', self.on_bind)
        factory.connect('unbind', self.on_unbind)
        self.listview.set_factory(factory)

    def on_setup(self, factory, list_item):
        card = MangaCard()
        card.thumbnail_task = None
        list_item.set_child(card)

    def on_bind(self, factory, list_item):
        item = list_item.get_item()
        card = list_item.get_child()
        card.model = item
        card.thumbnail_task = self.suwayomi.startThumbnail(item)

    def on_unbind(self, factory, list_item):
        card = list_item.get_child()
        self.suwayomi.stopThumbnail(list_item.get_item(), card.thumbnail_task)
        card.thumbnail_task = None
        card.model = None

    def on_activate(self, listview, position):
        item = self.store.get_item(position)
        listview.activate_action("app.show_manga", GLib.Variant("i", item.id))

    def remove_all(self):
        self.store.remove_all()

    def set_items(self, items: list):
        self.store.splice(0, self.store.get_n_items(), items)
