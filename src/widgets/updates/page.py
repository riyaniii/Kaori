import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ...integrations import models
from ...integrations.suwayomi import watch
from ..common.dates import day_title, to_datetime
from ..common.lists import sync_store
from .row import UpdatesRow

REFRESH_DELAY = 2


def first_unread(chapters):
    for chapter in reversed(chapters):
        if not chapter.is_read:
            return chapter
    return chapters[0]


def apply_chapters(entry):
    entry.update_data(
        chapter=first_unread(entry.chapters),
        chapter_count=len(entry.chapters),
        revision=entry.revision + 1,
    )


def add_to_entry(entry, chapter):
    if chapter in entry.chapters:
        return
    entry.chapters.append(chapter)
    apply_chapters(entry)


def set_entry_chapters(entry, chapters):
    chapters = list(chapters)
    if chapters == entry.chapters:
        return
    entry.chapters = chapters
    apply_chapters(entry)


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/updates/page.ui')
class UpdatesPage(Adw.NavigationPage):
    __gtype_name__ = "KaoriUpdatesPage"

    scrolled = Gtk.Template.Child()

    entries = GObject.Property(type=Gio.ListStore)
    updating = GObject.Property(type=bool, default=False)

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi

        self.entries = Gio.ListStore(item_type=models.UpdatesEntry)
        self.entry_by_key = {}
        self.offset = 0
        self.has_next = True
        self.loading = False
        self.generation = 0
        self.task = None
        self.refresh_id = 0

        watch(self, self.suwayomi, self.on_updates_changed, "notify::updates-revision")
        self.scrolled.get_vadjustment().connect("changed", self.on_adjustment_changed)
        self.suwayomi.bind_property("updating", self, "updating", GObject.BindingFlags.SYNC_CREATE)
        self.reload()

    def do_dispose(self):
        if self.refresh_id:
            GLib.source_remove(self.refresh_id)
            self.refresh_id = 0
        if self.task:
            self.task.cancel()
            self.task = None
        Adw.NavigationPage.do_dispose(self)

    def on_updates_changed(self):
        if self.refresh_id:
            GLib.source_remove(self.refresh_id)
        self.refresh_id = GLib.timeout_add_seconds(REFRESH_DELAY, self.on_refresh_due)

    def on_refresh_due(self):
        self.refresh_id = 0
        self.reload(True)
        return GLib.SOURCE_REMOVE

    def reload(self, silent: bool = False):
        self.generation += 1
        if self.task:
            self.task.cancel()
            self.task = None
        self.loading = False

        refresh = silent and self.entries.get_n_items() > 0
        if not refresh:
            self.clear()
        self.task = asyncio.create_task(self.load(refresh))

    def load_more(self):
        if self.loading or not self.has_next:
            return
        self.task = asyncio.create_task(self.load(False))

    async def fetch(self, refresh: bool) -> tuple[list, bool]:
        if not refresh:
            return await self.suwayomi.getUpdates(self.offset)

        wanted = max(self.offset, 1)
        chapters = []
        while True:
            batch, has_next = await self.suwayomi.getUpdates(len(chapters))
            chapters += batch
            if not batch or not has_next or len(chapters) >= wanted:
                return chapters, has_next

    async def load(self, refresh: bool):
        generation = self.generation
        self.loading = True

        try:
            chapters, has_next = await self.fetch(refresh)
        except Exception as error:
            if generation != self.generation:
                return
            print(f"updates load failed: {error}")
            self.loading = False
            return

        if generation != self.generation:
            return

        self.loading = False
        self.has_next = has_next

        if refresh:
            self.merge_entries(chapters)
            self.offset = len(chapters)
        else:
            created = []
            for chapter in chapters:
                self.add_chapter(chapter, self.entry_by_key, created)
            self.entries.splice(self.entries.get_n_items(), 0, created)
            self.offset += len(chapters)

    def merge_entries(self, chapters):
        entry_by_key = {}
        fresh = []
        for chapter in chapters:
            self.add_chapter(chapter, entry_by_key, fresh)

        merged = []
        for entry in fresh:
            key = (entry.day_number, entry.manga.id)
            existing = self.entry_by_key.get(key)
            if existing is None:
                merged.append(entry)
                continue
            set_entry_chapters(existing, entry.chapters)
            entry_by_key[key] = existing
            merged.append(existing)

        self.entry_by_key = entry_by_key
        sync_store(self.entries, merged)

    def clear(self):
        self.entries.remove_all()
        self.entry_by_key.clear()
        self.offset = 0
        self.has_next = True
        self.loading = False

    def add_chapter(self, chapter, entry_by_key, created):
        if chapter.manga is None:
            return

        moment = to_datetime(chapter.fetched_at)
        when = moment.date() if moment else None
        day_number = when.toordinal() if when else 0

        key = (day_number, chapter.manga.id)
        entry = entry_by_key.get(key)
        if entry is None:
            entry = models.UpdatesEntry(chapter.manga, day_number, day_title(when))
            entry_by_key[key] = entry
            created.append(entry)
        add_to_entry(entry, chapter)

    def open_chapter(self, chapter):
        self.activate_action(
            "app.show_reader",
            GLib.Variant("(ii)", (chapter.manga.id, chapter.id))
        )

    def on_row_resume(self, row, chapter):
        self.open_chapter(chapter)

    def on_adjustment_changed(self, adjustment):
        if self.loading or not self.has_next:
            return
        if self.entries.get_n_items() == 0:
            return
        if adjustment.get_upper() <= adjustment.get_page_size() + 1:
            self.load_more()

    @Gtk.Template.Callback()
    def get_page(self, obj, count):
        return "updates" if count > 0 else "greeter"

    @Gtk.Template.Callback()
    def on_setup(self, factory, list_item):
        list_item.set_activatable(True)
        row = UpdatesRow()
        row.connect("resume", self.on_row_resume)
        list_item.set_child(row)

    @Gtk.Template.Callback()
    def on_bind(self, factory, list_item):
        list_item.get_child().set_entry(list_item.get_item())

    @Gtk.Template.Callback()
    def on_unbind(self, factory, list_item):
        list_item.get_child().clear_entry()

    @Gtk.Template.Callback()
    def on_header_setup(self, factory, header):
        label = Gtk.Label(
            xalign=0, css_classes=["title-4"],
            margin_top=12, margin_bottom=6, margin_start=6,
        )
        header.set_child(label)

    @Gtk.Template.Callback()
    def on_header_bind(self, factory, header):
        header.get_child().set_label(header.get_item().day_title)

    @Gtk.Template.Callback()
    def on_activate(self, listview, position):
        entry = listview.get_model().get_item(position)
        if entry.chapter_count > 1:
            entry.expanded = not entry.expanded
        else:
            self.open_chapter(entry.chapter)

    @Gtk.Template.Callback()
    def on_edge_reached(self, scrolled, position):
        if position == Gtk.PositionType.BOTTOM:
            self.load_more()

    @Gtk.Template.Callback()
    def get_update_icon(self, obj, updating):
        return "process-stop-symbolic" if updating else "view-refresh-symbolic"

    @Gtk.Template.Callback()
    def get_update_tooltip(self, obj, updating):
        return _("Stop Updating") if updating else _("Update Library")

    @Gtk.Template.Callback()
    def on_update_clicked(self, button):
        if self.updating:
            asyncio.create_task(self.suwayomi.stopLibraryUpdate())
        else:
            asyncio.create_task(self.update_library())

    async def update_library(self):
        self.activate_action("app.show_toast", GLib.Variant("s", _("Updating library…")))
        try:
            await self.suwayomi.updateLibrary()
        except Exception as error:
            print("Library update failed:", error)
            self.activate_action("app.show_toast", GLib.Variant("s", _("Couldn't update the library")))
