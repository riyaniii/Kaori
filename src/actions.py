from gi.repository import Adw

from . import widgets as Widgets


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


def toggle_chapter_panel(app):
    window = get_window(app)
    stack_page = window.main_stack.get_visible_child().get_visible_page()
    reader_page = window.main_nav_view.get_visible_page()

    if not (isinstance(stack_page, Widgets.manga.MangaPage) or isinstance(reader_page, Widgets.reader.ReaderPage)):
        return

    split_view = window.overlay_split_view
    split_view.set_show_sidebar(not split_view.get_show_sidebar())


def edit_categories(app, manga_id: int):
    model = app.suwayomi.getModel(manga_id, 'Manga')
    get_window(app).category_panel.edit_categories(model)


def manage_categories(app):
    get_window(app).category_panel.manage_categories()


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
