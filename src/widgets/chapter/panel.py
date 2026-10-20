from gi.repository import Gtk, Adw, GLib, GObject

from ...integrations import models

from .row import ChapterRow

@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/chapter/panel.ui')
class ChapterPanel(Adw.NavigationPage):
    __gtype_name__ = "KaoriChapterPanel"

    chapter_list = Gtk.Template.Child()
    stack = Gtk.Template.Child()

    manga_model = GObject.Property(type=models.Manga)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.selection = Gtk.NoSelection()
        self.chapter_list.set_model(self.selection)
        self.chapter_list.connect('activate', self.on_activate)

        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', self.on_setup)
        factory.connect('bind', self.on_bind)
        self.chapter_list.set_factory(factory)

    def on_setup(self, factory, list_item):
        list_item.set_activatable(True)
        list_item.set_child(ChapterRow())

    def on_bind(self, factory, list_item):
        list_item.get_child().model = list_item.get_item()

    def on_activate(self, chapter_list, position):
        item = self.selection.get_item(position)
        chapter_list.activate_action(
            "app.show_reader",
            GLib.Variant("(ii)", (self.manga_model.id, item.id))
        )

    def set_manga_model(self, manga_model):
        self.manga_model = manga_model
        chapters = manga_model.chapters
        self.selection.set_model(chapters)
        self.stack.set_visible_child_name("list" if chapters.get_n_items() > 0 else "empty")
