import asyncio
from gettext import gettext as _

from gi.repository import Gdk, Gio, GObject, Gtk

from ...integrations import models
from .base import WEBTOON_ZOOM_MIN, ReaderBase, adjacent_chapter
from .canvas import Canvas
from .scroller import Scroller

PREFETCH_PAGES = 6
BANNER_RATIO = 2.2


class TransitionPage(models.Page):
    def __init__(self, chapter):
        super().__init__(index=-1, chapter_id=chapter.id, ratio=BANNER_RATIO)
        self.chapter = chapter


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/reader/webtoon.ui')
class WebtoonReader(ReaderBase):
    __gtype_name__ = "KaoriWebtoonReader"

    zoom_min = WEBTOON_ZOOM_MIN

    orientation = GObject.Property(type=Gtk.Orientation, default=Gtk.Orientation.VERTICAL)

    canvas = Gtk.Template.Child()
    scrolled_window = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_position = 0

        self.store = Gio.ListStore(item_type=models.Page)
        self.chapters = []
        self.loading = set()

        self.canvas.bind_store(self.store)
        for name in ("orientation", "direction"):
            self.bind_property(name, self.canvas, name, GObject.BindingFlags.SYNC_CREATE)
        self.canvas.connect("page-changed", self.on_page_changed)

        self.scroller = Scroller(self)

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

    def animate_zoom(self, value, x, y):
        self.scroller.stop_all()
        self.cancel_kinetic()
        super().animate_zoom(value, x, y)

    def on_pinch_begin(self, gesture, sequence):
        self.scroller.stop_all()
        self.cancel_kinetic()
        super().on_pinch_begin(gesture, sequence)

    def retry_failed(self):
        self.canvas.retry_failed()

    def cancel_kinetic(self):
        self.scrolled_window.set_kinetic_scrolling(False)
        self.scrolled_window.set_kinetic_scrolling(True)

    def on_user_scroll(self, controller, dx, dy):
        state = controller.get_current_event_state()
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        is_wheel = controller.get_unit() == Gdk.ScrollUnit.WHEEL
        if is_wheel and not ctrl and dy:
            self.scroller.wheel(dy)
            return Gdk.EVENT_STOP
        self.scroller.stop_all()
        return Gdk.EVENT_PROPAGATE

    def can_continue(self):
        return "after" in self.loading

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
        except Exception as error:
            print(f"chapter failed: {chapter.id}: {error}")
            self.show_toast(_("Couldn't load {}").format(chapter.title))
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
