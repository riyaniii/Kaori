import asyncio
from gi.repository import Gio, GLib, GObject, Gtk

from ...integrations import models
from .base import ReaderBase, adjacent_chapter
from .canvas import Canvas

PREFETCH_PAGES = 6
BANNER_RATIO = 2.2
SCROLL_SPEED = 800

class TransitionPage(models.Page):
    def __init__(self, chapter):
        super().__init__(index=-1, chapter_id=chapter.id)
        self.chapter = chapter


@Gtk.Template(resource_path='/com/rini/kaghez/reader/webtoon.ui')
class WebtoonReader(ReaderBase):
    __gtype_name__ = "KaghezWebtoonReader"

    orientation = GObject.Property(type=Gtk.Orientation, default=Gtk.Orientation.VERTICAL)

    canvas = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_position = 0

        self.store = Gio.ListStore(item_type=models.Page)
        self.chapters = []  # loaded chapter models, in strip order
        self.loading = set()  # which ends of the strip are being extended: "before", "after"

        self.scroll_direction = 0  # -1, 0 or 1 while an arrow key is held
        self.tick_id = 0
        self.last_frame_time = 0

        self.canvas.bind_store(self.store)
        for name in ("orientation", "direction"):
            self.bind_property(name, self.canvas, name, GObject.BindingFlags.SYNC_CREATE)
        self.canvas.connect("page-changed", self.on_page_changed)

        self.connect("notify::chapter-model", self.on_chapter_model_changed)

    def bind_store(self, store: Gio.ListStore):
        pass

    @GObject.Property(type=int, default=0)
    def position(self):
        return self.current_position

    @position.setter
    def position(self, value):
        count = self.page_count
        self.current_position = max(0, min(value, count - 1)) if count else 0
        index = self.store_index(self.chapter_model, self.current_position)
        if index is not None:
            self.canvas.scroll_to_index(index)

    @property
    def zoom(self):
        return self.canvas.zoom

    def zoom_to(self, value, x, y):
        self.canvas.set_zoom_anchored(value, x, y)

    def scroll_page(self, direction):
        self.canvas.scroll_page(direction)

    def start_scrolling(self, direction):
        self.scroll_direction = direction
        if not self.tick_id:
            self.last_frame_time = self.get_frame_clock().get_frame_time()
            self.tick_id = self.add_tick_callback(self.on_tick)

    def stop_scrolling(self):
        self.scroll_direction = 0

    def on_tick(self, widget, frame_clock):
        frame_time = frame_clock.get_frame_time()
        elapsed = (frame_time - self.last_frame_time) / GLib.USEC_PER_SEC
        self.last_frame_time = frame_time

        if not self.scroll_direction or not self.get_mapped():
            self.scroll_direction = 0
            self.tick_id = 0
            return GLib.SOURCE_REMOVE

        self.canvas.scroll_by(self.scroll_direction * SCROLL_SPEED * elapsed)
        return GLib.SOURCE_CONTINUE

    def find_chapter(self, chapter_id):
        return next((chapter for chapter in self.chapters if chapter.id == chapter_id), None)

    def store_index(self, chapter, position):
        if chapter is None:
            return None
        return next(
            (
                index
                for index, page in enumerate(self.store)
                if page.chapter_id == chapter.id and page.index == position
            ),
            None,
        )

    def on_chapter_model_changed(self, reader, pspec):
        chapter = self.chapter_model
        if chapter is None or self.find_chapter(chapter.id) is not None:
            return
        self.chapters = []
        self.store.remove_all()
        asyncio.create_task(self.load_chapter_pages(chapter, prepend=False))

    async def load_chapter_pages(self, chapter, prepend: bool):
        side = "before" if prepend else "after"
        self.loading.add(side)
        try:
            pages = await self.suwayomi.getChapterPages(chapter.id)
        except Exception:
            return
        finally:
            self.loading.discard(side)

        banner = [TransitionPage(chapter)] if self.chapters else []
        block = banner + pages

        if prepend:
            self.chapters.insert(0, chapter)
            banner_index = 0
        else:
            self.chapters.append(chapter)
            banner_index = self.store.get_n_items()
        self.store.splice(banner_index, 0, block)

        if banner:
            self.canvas.set_ratio(banner_index, BANNER_RATIO)

        self.position = self.current_position

    def maybe_prefetch(self, page):
        if not self.chapters:
            return

        leading, trailing = self.chapters[0], self.chapters[-1]

        near_start = page.chapter_id == leading.id and page.index < PREFETCH_PAGES
        if near_start and "before" not in self.loading:
            if previous := adjacent_chapter(self.manga_model, leading, -1):
                asyncio.create_task(self.load_chapter_pages(previous, prepend=True))

        near_end = page.chapter_id == trailing.id and trailing.page_count - page.index <= PREFETCH_PAGES
        if near_end and "after" not in self.loading:
            if following := adjacent_chapter(self.manga_model, trailing, 1):
                asyncio.create_task(self.load_chapter_pages(following, prepend=False))

    def on_page_changed(self, canvas, index):
        page = self.store.get_item(index)
        self.maybe_prefetch(page)

        if page.index < 0:  # sitting on a banner page, between chapters
            return

        if page.chapter_id != self.chapter_model.id:
            self.mark_chapter_read(self.chapter_model)
            self.chapter_model = self.find_chapter(page.chapter_id)

        if page.index != self.current_position:
            self.current_position = page.index
            self.notify("position")

    def mark_chapter_read(self, chapter):
        if chapter.is_read:
            return
        asyncio.create_task(
            self.suwayomi.updateChapter(
                chapter_id=chapter.id,
                is_read=True,
                last_page_read=chapter.page_count,
            )
        )
