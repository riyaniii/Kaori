import re
import asyncio
from gi.repository import Gtk, Adw, GObject, Gio, GLib

from ...integrations import models

from .card import MangaCard

def markdown_to_pango(md: str) -> str:
    if md is None:
        return
    def inline(text: str) -> str:
        text = GLib.markup_escape_text(text or "")

        text = re.sub(
            r"`([^`]+)`",
            r'<tt>\1</tt>',
            text,
        )

        text = re.sub(
            r"\*\*(.+?)\*\*",
            r"<b>\1</b>",
            text,
        )

        text = re.sub(
            r"(?<!\*)\*(.+?)\*(?!\*)",
            r"<i>\1</i>",
            text,
        )

        text = re.sub(
            r"\[(.*?)\]\((.*?)\)",
            r'<a href="\2">\1</a>',
            text,
        )

        return text

    lines = md.splitlines()
    out = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            out.append("")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            size = {
                1: "xx-large",
                2: "x-large",
                3: "large",
                4: "medium",
                5: "small",
                6: "small",
            }[level]

            out.append(
                f'<span size="{size}" weight="bold">{inline(m.group(2))}</span>'
            )
            continue

        m = re.match(r"^[-*]\s+(.*)$", stripped)
        if m:
            out.append(f"• {inline(m.group(1))}")
            continue

        out.append(inline(line))

    return "\n".join(out)


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/manga/page.ui')
class MangaPage(Adw.NavigationPage):
    __gtype_name__ = "KaoriMangaPage"

    model = GObject.Property(type=models.Manga)

    genres = Gtk.Template.Child()

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.suwayomi = Gio.Application.get_default().suwayomi

        self.actions = Gio.SimpleActionGroup()
        self.insert_action_group("manga", self.actions)

        self.add_manga_action("read", self.on_read)
        self.add_manga_action("toggle_library", self.on_toggle_library)
        self.add_manga_action("refresh", self.on_refresh)
        self.add_manga_action("download", self.on_download, GLib.VariantType.new("s"))

    def add_manga_action(self, name, callback, param_type=None):
        action = Gio.SimpleAction.new(name, param_type)
        action.connect("activate", callback)
        self.actions.add_action(action)

    def show_toast(self, message):
        overlay = self.get_root().toast_overlay
        overlay.dismiss_all()
        overlay.add_toast(Adw.Toast(title=message, timeout=1, use_markup=False))

    @Gtk.Template.Callback()
    def on_shown(self, *args):
        if self.model.initialized:
            asyncio.create_task(self.load_chapters())
        else:
            asyncio.create_task(self.load_manga())

    async def load_manga(self):
        await self.suwayomi.getManga(self.model.id)
        self.refresh_chapter_panel()

    async def load_chapters(self):
        await self.suwayomi.getChapters(self.model.id)
        self.refresh_chapter_panel()
        if self.model.total_chapters == 0:
            await self.refresh(False)

    def on_refresh(self, *args):
        asyncio.create_task(self.refresh(True))

    async def refresh(self, notify):
        action = self.actions.lookup_action("refresh")
        action.set_enabled(False)
        try:
            await self.suwayomi.refreshManga(self.model.id)
        except Exception:
            if notify:
                self.show_toast("Refresh failed")
            return
        finally:
            action.set_enabled(True)
        self.refresh_chapter_panel()
        if notify:
            self.show_toast(f"{self.model.total_chapters} chapters")

    def refresh_chapter_panel(self):
        self.activate_action("app.set_chapters", GLib.Variant("i", self.model.id))

    def on_read(self, *args):
        if not self.model.last_read_chapter:
            return
        self.activate_action(
            "app.show_reader",
            GLib.Variant("(ii)", (self.model.id, self.model.last_read_chapter.id))
        )

    def on_toggle_library(self, *args):
        asyncio.create_task(self.toggle_library())

    def on_download(self, action, param):
        asyncio.create_task(self.download_chapters(int(param.get_string())))

    async def toggle_library(self):
        model = self.model
        was_in_library = model.in_library

        await self.suwayomi.setMangaLibrary(model.id, not was_in_library)

        verb = "removed from" if was_in_library else "added to"
        self.show_toast(f"{model.title} {verb} library")

    async def download_chapters(self, count):
        pending = [
            chapter for chapter in sorted(self.model.chapters, key=lambda c: c.source_order)
            if not chapter.is_downloaded
        ]
        if count != 0:
            pending = [chapter for chapter in pending if not chapter.is_read]
        if count > 0:
            pending = pending[:count]

        if not pending:
            self.show_toast("Nothing to download")
            return

        for chapter in pending:
            await self.suwayomi.enqueueChapterDownload(chapter.id)

        noun = "chapter" if len(pending) == 1 else "chapters"
        self.show_toast(f"Downloading {len(pending)} {noun}")

    @Gtk.Template.Callback()
    def populate_genres(self, obj, genre):
        while child := self.genres.get_first_child():
            self.genres.remove(child)
        for name in genre or []:
            self.genres.append(Gtk.Button(label=name))
        return bool(genre)

    @Gtk.Template.Callback()
    def get_read_button_label(self, obj, chapter):
        if chapter == None:
            return "..."
        if chapter.source_order > 1:
            return "Continue"
        return "Start"

    @Gtk.Template.Callback()
    def get_library_icon_name(self, obj, in_library):
        return "heart-filled-symbolic" if in_library else "heart-outline-thick-symbolic"

    @Gtk.Template.Callback()
    def get_library_button_tooltip(self, obj, in_library):
        return "Remove from library" if in_library else "Add to library"

    @Gtk.Template.Callback()
    def get_description(self, obj, description):
        return markdown_to_pango(description)
