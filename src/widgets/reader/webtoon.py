import asyncio
import math
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from ...integrations import models
from .base import ReaderBase, adjacent_chapter
from .canvas import Canvas

PREFETCH_PAGES = 6
BANNER_RATIO = 2.2
SCROLL_SPEED = 800
SCROLL_ACCEL_TIME = 0.08
SCROLL_DECEL_TIME = 0.18
SCROLL_STOP_SPEED = 5
MAX_FRAME_DELTA = 0.05
PAGE_SCROLL_DURATION = 250
PAGE_SCROLL_RATIO = 0.9


class TransitionPage(models.Page):
    def __init__(self, chapter):
        super().__init__(index=-1, chapter_id=chapter.id, ratio=BANNER_RATIO)
        self.chapter = chapter


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/reader/webtoon.ui')
class WebtoonReader(ReaderBase):
    __gtype_name__ = "KaoriWebtoonReader"

    orientation = GObject.Property(type=Gtk.Orientation, default=Gtk.Orientation.VERTICAL)

    canvas = Gtk.Template.Child()
    scrolled_window = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_position = 0

        self.store = Gio.ListStore(item_type=models.Page)
        self.chapters = []
        self.loading = set()

        self.scroll_direction = 0
        self.scroll_velocity = 0.0
        self.tick_id = 0
        self.last_frame_time = 0

        self.page_animation = None
        self.page_progress = 0.0
        self.page_target = 0.0

        self.canvas.bind_store(self.store)
        for name in ("orientation", "direction"):
            self.bind_property(name, self.canvas, name, GObject.BindingFlags.SYNC_CREATE)
        self.canvas.connect("page-changed", self.on_page_changed)

        self.connect("notify::chapter-model", self.on_chapter_model_changed)

        user_scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES,
            propagation_phase=Gtk.PropagationPhase.CAPTURE,
        )
        user_scroll.connect("scroll", self.on_user_scroll)
        self.add_controller(user_scroll)

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

    def cancel_kinetic(self):
        self.scrolled_window.set_kinetic_scrolling(False)
        self.scrolled_window.set_kinetic_scrolling(True)

    def cancel_keyboard_scroll(self):
        self.scroll_direction = 0
        self.scroll_velocity = 0.0
        self.cancel_page_scroll()

    def on_user_scroll(self, controller, dx, dy):
        self.cancel_keyboard_scroll()
        return Gdk.EVENT_PROPAGATE

    def scroll_page(self, direction):
        self.cancel_kinetic()
        horizontal = self.orientation == Gtk.Orientation.HORIZONTAL
        size = self.canvas.get_width() if horizontal else self.canvas.get_height()
        distance = direction * size * PAGE_SCROLL_RATIO

        if self.page_animation is not None:
            distance += self.page_target - self.page_progress
            self.page_animation.pause()

        self.page_progress = 0.0
        self.page_target = distance
        self.page_animation = Adw.TimedAnimation.new(
            self,
            0.0,
            distance,
            PAGE_SCROLL_DURATION,
            Adw.CallbackAnimationTarget.new(self.on_page_scroll),
        )
        self.page_animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.page_animation.connect("done", self.on_page_scroll_done)
        self.page_animation.play()

    def on_page_scroll(self, value):
        self.canvas.scroll_by(value - self.page_progress)
        self.page_progress = value

    def on_page_scroll_done(self, animation):
        if animation is self.page_animation:
            self.page_animation = None

    def cancel_page_scroll(self):
        if self.page_animation is not None:
            self.page_animation.pause()
            self.page_animation = None

    def start_scrolling(self, direction):
        if direction != self.scroll_direction:
            self.cancel_kinetic()
        self.cancel_page_scroll()
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
        elapsed = min(max(elapsed, 0.0), MAX_FRAME_DELTA)

        if not self.get_mapped():
            self.scroll_direction = 0
            self.scroll_velocity = 0.0
            self.tick_id = 0
            return GLib.SOURCE_REMOVE

        target = self.scroll_direction * SCROLL_SPEED
        tau = SCROLL_ACCEL_TIME if self.scroll_direction else SCROLL_DECEL_TIME
        self.scroll_velocity += (target - self.scroll_velocity) * (1 - math.exp(-elapsed / tau))

        if not self.scroll_direction and abs(self.scroll_velocity) < SCROLL_STOP_SPEED:
            self.scroll_velocity = 0.0
            self.tick_id = 0
            return GLib.SOURCE_REMOVE

        self.canvas.scroll_by(self.scroll_velocity * elapsed)
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

        first_load = not self.chapters
        banner = [] if first_load else [TransitionPage(chapter)]
        block = banner + pages

        if prepend:
            self.chapters.insert(0, chapter)
            insert_at = 0
        else:
            self.chapters.append(chapter)
            insert_at = self.store.get_n_items()
        self.store.splice(insert_at, 0, block)

        if first_load:
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

        if page.index < 0:
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
