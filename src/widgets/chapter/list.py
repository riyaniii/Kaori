from gi.repository import GObject, Gtk

from ...integrations import models
from .row import ChapterRow


class ChapterList(Gtk.ListView):
    __gtype_name__ = "KaoriChapterList"
    __gsignals__ = {
        "chapter-activated": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    options = GObject.Property(type=models.ChapterOptions)

    def __init__(self, **kwargs):
        super().__init__(single_click_activate=True, **kwargs)
        self.add_css_class("navigation-sidebar")
        self.add_css_class("inherit-color")
        self.options = models.ChapterOptions()

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_setup)
        factory.connect("bind", self.on_bind)
        self.set_factory(factory)
        self.connect("activate", self.on_activate)

    def set_chapters(self, chapters):
        self.set_model(Gtk.NoSelection(model=chapters))

    def on_setup(self, factory, list_item):
        list_item.set_child(ChapterRow())

    def on_bind(self, factory, list_item):
        row = list_item.get_child()
        row.options = self.options
        row.model = list_item.get_item()

    def on_activate(self, list_view, position):
        chapter = self.get_model().get_item(position)
        if chapter is not None:
            self.emit("chapter-activated", chapter)
