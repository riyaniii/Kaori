from gi.repository import Adw, Gio
from kaghez.widgets.reader.page import ReaderPage
import asyncio

from . import widgets as Widgets

async def set_chapters(app, manga_id: int):
    model = app.suwayomi.getModel(manga_id, 'Manga')

    window = app.get_active_window()
    chapter_panel = window.chapter_panel
    chapter_panel.set_manga_model(model)

def toggle_chapter_panel(app):
    window = app.get_active_window()

    current_page = window.main_stack.get_visible_child().get_visible_page()
    maybe_reader = window.main_nav_view.get_visible_page()
    if isinstance(current_page, Widgets.manga.MangaPage) or isinstance(maybe_reader, ReaderPage):
        split_view = window.overlay_split_view
        split_view.set_show_sidebar(not split_view.get_show_sidebar())
    else:
        return

def switch_page(app, name: str):
    window = app.get_active_window()
    window.main_stack.set_visible_child_name(name)

def open_search_page(app):
    window = app.get_active_window()
    window.main_stack.set_visible_child_name('search')

def open_downloads_page(app):
    window = app.get_active_window()
    window.main_stack.set_visible_child_name('downloads')

def open_library_page(app):
    window = app.get_active_window()
    window.main_stack.set_visible_child_name('library')

def show_page(app, page: Adw.NavigationPage):
    window = app.get_active_window()
    nav_view = window.main_stack.get_visible_child()
    nav_view.push(page)

def show_dialog(app, dialog: Adw.Dialog):
    window = app.get_active_window()
    nav_view = window.main_stack.get_visible_child()

    dialog.present(nav_view)

async def show_reader(app, manga_id: int, chapter_id: int):
    manga_model = app.suwayomi.getModel(manga_id, 'Manga')
    chapter_model = app.suwayomi.getModel(chapter_id, 'Chapter')

    nav_view = app.get_active_window().main_nav_view

    page = Widgets.reader.ReaderPage(manga_model, chapter_model)

    nav_view.push(page)


async def show_extension(app, pkg_name: str):
    model = app.suwayomi.getModel(pkg_name, 'Extension')

    dialog = Widgets.extension.ExtensionDialog(model)
    show_dialog(app, dialog)


async def show_source(app, source_id: str):
    model = app.suwayomi.getModel(source_id, 'Source')

    page = Widgets.source.SourcePage(model)
    show_page(app, page)

async def show_manga(app, manga_id: int):
    model = app.suwayomi.getModel(manga_id, 'Manga')

    page = Widgets.manga.MangaPage(model)
    show_page(app, page)


async def extension_action(app, pkg_name: str):
    model = app.suwayomi.getModel(pkg_name, 'Extension')

    if model.has_update:
        await app.suwayomi.updateExtension(model.pkg_name)
    elif model.is_installed:
        await app.suwayomi.uninstallExtension(model.pkg_name)
    else:
        await app.suwayomi.installExtension(model.pkg_name)

def show_toast(app, message: str):
    window = app.get_active_window()
    toast_overlay = window.toast_overlay
    toast_overlay.dismiss_all()

    toast = Adw.Toast.new(message)
    toast.set_timeout(1)
    toast_overlay.add_toast(toast)

async def toggle_library(app, manga_id: int):
    model = app.suwayomi.getModel(manga_id, 'Manga')

    if not model.in_library:
        await app.suwayomi.addToLibrary(model.id)
        show_toast(app, f"{model.title} added to library")
    else:
        await app.suwayomi.removeFromLibrary(model.id)
        show_toast(app, f"{model.title} removed from library")

async def download_chapter(app, chapter_id: int):
    model = app.suwayomi.getModel(chapter_id, 'Chapter')

    await app.suwayomi.enqueueChapterDownload(chapter_id)
    show_toast(app, f"Downloading {model.name}")

async def delete_chapter_download(app, chapter_id: int):
    model = app.suwayomi.getModel(chapter_id, 'Chapter')

    await app.suwayomi.deleteDownloadedChapter(chapter_id)
    show_toast(app, f"Deleted download of {model.name}")
