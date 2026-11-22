import asyncio

from gi.repository import Adw, Gio, GLib, Gtk

from .. import actions
from .main_view import KaoriMainView

VIEW_PARTS = (
    "main_stack",
    "category_split_view",
    "category_panel",
    "overlay_split_view",
    "main_nav_view",
    "toast_overlay",
    "chapter_panel",
)


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/window.ui')
class KaoriWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'KaoriWindow'

    window_stack = Gtk.Template.Child()
    main_bin = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.main_view = None

    def show_start(self):
        self.main_view = None
        self.main_bin.set_child(None)
        self.window_stack.set_visible_child_name("start")

    def show_main(self):
        self.main_view = KaoriMainView()
        for name in VIEW_PARTS:
            setattr(self, name, getattr(self.main_view, name))
        self.main_bin.set_child(self.main_view)
        self.add_actions()
        self.window_stack.set_visible_child_name("main")

    def add_actions(self):
        self.create_action(actions.show_manga, parameter_type="i")
        self.create_action(actions.show_reader, parameter_type="(ii)")
        self.create_action(actions.set_chapters, parameter_type="i")
        self.create_action(actions.toggle_chapter_panel, ['<control>s'], parameter_type=None)
        self.create_action(actions.show_source)
        self.create_action(actions.show_extension)
        self.create_action(actions.switch_page)
        self.create_action(actions.show_toast)
        self.create_action(actions.open_search_page, ['<control>f', '<control>k'], parameter_type=None)
        self.create_action(actions.open_downloads_page, ['<control>j'], parameter_type=None)
        self.create_action(actions.open_library_page, ['<control>l'], parameter_type=None)
        self.create_action(actions.edit_categories, parameter_type="i")
        self.create_action(actions.manage_categories, parameter_type=None)
        self.add_action(Gio.PropertyAction.new(
            "show-categories", self.category_split_view, "show-sidebar"))

    def create_action(self, callback: callable, shortcuts: list | None = None, parameter_type: str = "s"):
        shortcuts = shortcuts or []

        def call_action(action, variant):
            app = self.get_application()
            if variant is None:
                result = callback(app)
            else:
                value = variant.unpack()
                result = callback(app, *value) if isinstance(value, tuple) else callback(app, value)
            if asyncio.iscoroutine(result):
                task = asyncio.create_task(result)
                task.add_done_callback(
                    lambda t: t.exception() and print(f"Action '{callback.__name__}' failed:", t.exception())
                )

        self.get_application().create_action(
            name=callback.__name__,
            callback=call_action,
            shortcuts=shortcuts,
            parameter_type=GLib.VariantType.new(parameter_type) if parameter_type else None
        )
