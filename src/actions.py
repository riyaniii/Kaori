from gi.repository import Adw, Gtk

from . import widgets as Widgets
from .constants import GUIDE_URL, NAME, WELCOME_BODY


def get_window(app):
    return app.get_active_window()


def switch_page(app, name: str):
    get_window(app).main_stack.set_visible_child_name(name)


def open_search_page(app):
    switch_page(app, 'search')


def open_downloads_page(app):
    switch_page(app, 'downloads')


def open_library_page(app):
    switch_page(app, 'library')


def show_page(app, page: Adw.NavigationPage):
    get_window(app).main_stack.get_visible_child().push(page)


def show_dialog(app, dialog: Adw.Dialog):
    dialog.present(get_window(app))


def show_toast(app, message: str):
    toast_overlay = get_window(app).toast_overlay
    toast_overlay.dismiss_all()
    toast_overlay.add_toast(Adw.Toast(title=message, timeout=1, use_markup=False))


def on_welcome_response(dialog, response, app):
    app.settings.set_boolean('welcome-shown', True)
    if response == "guide":
        Gtk.UriLauncher(uri=GUIDE_URL).launch(get_window(app), None, None)


def show_welcome(app):
    dialog = Adw.AlertDialog(heading=f"Welcome to {NAME}", body=WELCOME_BODY)
    dialog.add_response("close", "Got It")
    dialog.add_response("guide", "Open Guide")
    dialog.set_response_appearance("guide", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("guide")
    dialog.set_close_response("close")
    dialog.connect("response", on_welcome_response, app)
    show_dialog(app, dialog)


def toggle_chapter_panel(app):
    window = get_window(app)
    stack_page = window.main_stack.get_visible_child().get_visible_page()
    reader_page = window.main_nav_view.get_visible_page()

    if not (isinstance(stack_page, Widgets.manga.MangaPage) or isinstance(reader_page, Widgets.reader.ReaderPage)):
        return

    split_view = window.overlay_split_view
    split_view.set_show_sidebar(not split_view.get_show_sidebar())


async def set_chapters(app, manga_id: int):
    model = app.suwayomi.getModel(manga_id, 'Manga')
    get_window(app).chapter_panel.set_manga_model(model)


async def show_reader(app, manga_id: int, chapter_id: int):
    manga_model = app.suwayomi.getModel(manga_id, 'Manga')
    chapter_model = app.suwayomi.getModel(chapter_id, 'Chapter')
    get_window(app).main_nav_view.push(Widgets.reader.ReaderPage(manga_model, chapter_model))


async def show_extension(app, pkg_name: str):
    model = app.suwayomi.getModel(pkg_name, 'Extension')
    show_dialog(app, Widgets.extension.ExtensionDialog(model))


async def show_source(app, source_id: str):
    model = app.suwayomi.getModel(source_id, 'Source')
    show_page(app, Widgets.source.SourcePage(model))


async def show_manga(app, manga_id: int):
    model = app.suwayomi.getModel(manga_id, 'Manga')
    show_page(app, Widgets.manga.MangaPage(model))
