import asyncio

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ...integrations import models
from ...integrations.suwayomi import watch
from ..common.dates import day_title, to_datetime
from ..common.lists import sync_store
from .row import HistoryRow

REFRESH_DELAY = 2


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/history/page.ui')
class HistoryPage(Adw.NavigationPage):
    __gtype_name__ = "KaoriHistoryPage"

    scrolled = Gtk.Template.Child()

    entries = GObject.Property(type=Gio.ListStore)
    state = GObject.Property(type=str, default="loading")
    error_message = GObject.Property(type=str, default="")
    loading_more = GObject.Property(type=bool, default=False)

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi

        self.entries = Gio.ListStore(item_type=models.HistoryEntry)
        self.entry_by_key = {}
        self.offset = 0
        self.has_next = True
        self.loading = False
        self.load_failed = False
        self.generation = 0
        self.task = None
        self.refresh_id = 0

        watch(self, self.suwayomi, self.on_history_changed, "notify::history-revision")
        self.scrolled.get_vadjustment().connect("changed", self.on_adjustment_changed)
        self.reload()

    def do_dispose(self):
        if self.refresh_id:
            GLib.source_remove(self.refresh_id)
            self.refresh_id = 0
        if self.task:
            self.task.cancel()
            self.task = None
        Adw.NavigationPage.do_dispose(self)

    def on_history_changed(self):
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
        self.loading_more = False

        refresh = silent and self.entries.get_n_items() > 0
        if not refresh:
            self.clear()
            self.state = "loading"
        self.task = asyncio.create_task(self.load(refresh))

    def load_more(self):
        if self.loading or not self.has_next:
            return
        self.task = asyncio.create_task(self.load(False))

    async def fetch(self, refresh: bool) -> tuple[list, bool]:
        if not refresh:
            return await self.suwayomi.getHistory(self.offset)

        wanted = max(self.offset, 1)
        chapters = []
        while True:
            batch, has_next = await self.suwayomi.getHistory(len(chapters))
            chapters += batch
            if not batch or not has_next or len(chapters) >= wanted:
                return chapters, has_next

    async def load(self, refresh: bool):
        generation = self.generation
        offset = 0 if refresh else self.offset
        self.loading = True
        self.load_failed = False
        self.loading_more = offset > 0

        try:
            chapters, has_next = await self.fetch(refresh)
        except Exception as error:
            if generation != self.generation:
                return
            print(f"history load failed: {error}")
            self.loading = False
            self.loading_more = False
            if self.entries.get_n_items() > 0:
                self.load_failed = True
            else:
                self.error_message = str(error)
                self.state = "error"
            return

        if generation != self.generation:
            return

        self.loading = False
        self.loading_more = False
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

        if self.entries.get_n_items() > 0:
            self.state = "list"
        elif not has_next:
            self.state = "empty"

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
            existing.set_chapters(entry.chapters)
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
        self.load_failed = False

    def add_chapter(self, chapter, entry_by_key, created):
        if chapter.manga is None:
            return

        moment = to_datetime(chapter.last_read_at)
        when = moment.date() if moment else None
        day_number = when.toordinal() if when else 0

        key = (day_number, chapter.manga.id)
        entry = entry_by_key.get(key)
        if entry is None:
            entry = models.HistoryEntry(chapter.manga, day_number, day_title(when))
            entry_by_key[key] = entry
            created.append(entry)
        entry.add_chapter(chapter)

    def open_chapter(self, chapter):
        self.activate_action(
            "app.show_reader",
            GLib.Variant("(ii)", (chapter.manga.id, chapter.id))
        )

    def on_row_resume(self, row, chapter):
        self.open_chapter(chapter)

    def on_adjustment_changed(self, adjustment):
        if self.load_failed or self.loading or not self.has_next:
            return
        if self.entries.get_n_items() == 0:
            return
        if adjustment.get_upper() <= adjustment.get_page_size() + 1:
            self.load_more()

    @Gtk.Template.Callback()
    def on_setup(self, factory, list_item):
        list_item.set_activatable(True)
        row = HistoryRow()
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
        label = header.get_child()
        label.set_label(header.get_item().day_title)

    @Gtk.Template.Callback()
    def on_activate(self, listview, position):
        entry = listview.get_model().get_item(position)
        if entry.chapter_count > 1:
            entry.expanded = not entry.expanded

    @Gtk.Template.Callback()
    def on_retry_clicked(self, button):
        self.reload()

    @Gtk.Template.Callback()
    def on_edge_reached(self, scrolled, position):
        if position == Gtk.PositionType.BOTTOM:
            self.load_failed = False
            self.load_more()
