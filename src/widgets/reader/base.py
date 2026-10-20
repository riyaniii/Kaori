import asyncio

from gi.repository import Adw, Gdk, Gio, GObject, Gtk

from ...integrations import models

ZOOM_MIN = 1.0
ZOOM_MAX = 4.0
ZOOM_STEP = 1.25
PIXELS_PER_STEP = 40
PREFETCH_SPREADS = 2


def adjacent_chapter(manga, chapter, direction):
    if manga is None or chapter is None:
        return None

    found, index = manga.chapters.find(chapter)
    if not found:
        return None

    new_index = index + direction
    if new_index < 0 or new_index >= manga.chapters.get_n_items():
        return None
    return manga.chapters.get_item(new_index)


class ReaderBase(Adw.Bin):
    __gtype_name__ = "KaoriReaderBase"

    chapter_model = GObject.Property(type=models.Chapter)
    manga_model = GObject.Property(type=models.Manga)

    step = 1

    @GObject.Signal(arg_types=(int,))
    def chapter_requested(self, direction):
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.store = None
        self.pointer = (0.0, 0.0)
        self.pinch_start = 1.0

        motion = Gtk.EventControllerMotion(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        motion.connect("enter", self.on_pointer_moved)
        motion.connect("motion", self.on_pointer_moved)
        self.add_controller(motion)

        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.VERTICAL,
            propagation_phase=Gtk.PropagationPhase.CAPTURE,
        )
        scroll.connect("scroll", self.on_scroll)
        self.add_controller(scroll)

        pinch = Gtk.GestureZoom(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        pinch.connect("begin", self.on_pinch_begin)
        pinch.connect("scale-changed", self.on_pinch_scale_changed)
        self.add_controller(pinch)

        double_tap = Gtk.GestureClick(button=0)
        double_tap.connect("pressed", self.on_double_tap)
        self.add_controller(double_tap)

    @GObject.Property(type=Gtk.TextDirection, default=Gtk.TextDirection.LTR)
    def direction(self):
        return self.get_direction()

    @direction.setter
    def direction(self, value):
        self.set_direction(value)

    @property
    def page_count(self):
        if self.chapter_model:
            return self.chapter_model.page_count
        return 0

    def bind_store(self, store: Gio.ListStore):
        self.store = store

    def next_page(self):
        self.position += 1

    def previous_page(self):
        self.position -= 1

    def zoom_to(self, value, x, y):
        raise NotImplementedError

    def zoom_by(self, factor):
        center_x = self.get_width() / 2
        center_y = self.get_height() / 2
        self.zoom_to(self.zoom * factor, center_x, center_y)

    def zoom_in(self):
        self.zoom_by(ZOOM_STEP)

    def zoom_out(self):
        self.zoom_by(1 / ZOOM_STEP)

    def reset_zoom(self):
        self.zoom_to(1.0, self.get_width() / 2, self.get_height() / 2)

    def on_pointer_moved(self, controller, x, y):
        self.pointer = (x, y)

    def on_scroll(self, controller, dx, dy):
        state = controller.get_current_event_state()
        if not state & Gdk.ModifierType.CONTROL_MASK:
            return Gdk.EVENT_PROPAGATE

        if controller.get_unit() == Gdk.ScrollUnit.WHEEL:
            steps = dy
        else:
            steps = dy / PIXELS_PER_STEP

        pointer_x, pointer_y = self.pointer
        self.zoom_to(self.zoom * ZOOM_STEP ** -steps, pointer_x, pointer_y)
        return Gdk.EVENT_STOP

    def on_pinch_begin(self, gesture, sequence):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.pinch_start = self.zoom

    def on_pinch_scale_changed(self, gesture, scale):
        found, x, y = gesture.get_bounding_box_center()
        if found:
            self.zoom_to(self.pinch_start * scale, x, y)

    def on_double_tap(self, gesture, n_press, x, y):
        if n_press == 2:
            self.zoom_to(1.0, x, y)


class PagedReader(ReaderBase):
    __gtype_name__ = "KaoriPagedReader"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.zoom = 1.0
        self.current_position = 0
        self.tasks = {}
        self.groups = {}
        self.drag_origin = (0.0, 0.0)

        window = self.scrolled_window
        window.get_hadjustment().connect("notify::page-size", self.on_viewport_resized)
        window.get_vadjustment().connect("notify::page-size", self.on_viewport_resized)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        self.add_controller(drag)

        self.connect("map", self.on_mapped)

    @property
    def pictures(self):
        raise NotImplementedError

    @property
    def content(self):
        raise NotImplementedError

    @property
    def scrolled_window(self):
        return self.get_child()

    @property
    def step(self):
        return len(self.pictures)

    @GObject.Property(type=int, default=0)
    def position(self):
        return self.current_position

    @position.setter
    def position(self, value):
        count = self.page_count
        if count == 0:
            self.current_position = 0
            return

        value = max(0, min(value, count - 1))
        self.current_position = value - value % self.step
        self.show_current()

    def next_page(self):
        count = self.page_count
        if count == 0:
            return

        if self.current_position + self.step >= count:
            self.emit("chapter-requested", 1)
        else:
            self.position += self.step

    def previous_page(self):
        if self.page_count == 0:
            return

        if self.current_position == 0:
            self.emit("chapter-requested", -1)
        else:
            self.position -= self.step

    def page_at(self, index):
        if 0 <= index < self.page_count:
            return self.store.get_item(index)
        return None

    def binding_group(self, picture):
        group = self.groups.get(picture)
        if group is None:
            group = GObject.BindingGroup()
            group.bind("paintable", picture, "paintable", GObject.BindingFlags.SYNC_CREATE)
            self.groups[picture] = group
        return group

    def on_mapped(self, reader):
        self.show_current()

    def show_current(self):
        if self.store is None or not self.get_mapped():
            return

        self.reset_zoom()
        for offset, picture in enumerate(self.pictures):
            page = self.page_at(self.current_position + offset)
            picture.set_paintable(None)
            self.binding_group(picture).set_source(page)
        self.refresh_window()

    def wanted_pages(self):
        start = self.current_position
        step = self.step
        indexes = list(range(start, start + step * (1 + PREFETCH_SPREADS)))
        indexes += list(range(start - step, start))
        pages = (self.page_at(index) for index in indexes)
        return [page for page in pages if page is not None]

    def refresh_window(self):
        wanted = self.wanted_pages()

        for page in self.store:
            if page in wanted:
                continue
            task = self.tasks.pop(page, None)
            if task:
                task.cancel()
            if page.paintable is not None:
                page.paintable = None

        for page in wanted:
            if page.paintable is None and page.url and page not in self.tasks:
                self.start_load(page)

    def start_load(self, page):
        task = asyncio.create_task(self.suwayomi.loadPage(page))
        self.tasks[page] = task
        task.add_done_callback(lambda done, page=page: self.forget_task(page, done))

    def forget_task(self, page, task):
        if self.tasks.get(page) is task:
            del self.tasks[page]

    def zoom_to(self, value, x, y):
        value = max(ZOOM_MIN, min(ZOOM_MAX, value))
        if abs(value - self.zoom) < 1e-6:
            return

        ratio = value / self.zoom
        self.zoom = value
        self.apply_zoom()

        window = self.scrolled_window
        self.rescale(window.get_hadjustment(), x, ratio)
        self.rescale(window.get_vadjustment(), y, ratio)

    def apply_zoom(self):
        if self.zoom <= ZOOM_MIN:
            self.content.set_size_request(-1, -1)
            return

        window = self.scrolled_window
        width = window.get_hadjustment().get_page_size()
        height = window.get_vadjustment().get_page_size()
        self.content.set_size_request(round(width * self.zoom), round(height * self.zoom))

    def rescale(self, adjustment, anchor, ratio):
        position = (adjustment.get_value() + anchor) * ratio - anchor
        adjustment.set_upper(adjustment.get_page_size() * self.zoom)
        adjustment.set_value(position)

    def on_viewport_resized(self, adjustment, pspec):
        if self.zoom > ZOOM_MIN:
            self.apply_zoom()

    def on_drag_begin(self, gesture, x, y):
        source = gesture.get_device().get_source()
        is_touch = source == Gdk.InputSource.TOUCHSCREEN
        if is_touch or self.zoom <= ZOOM_MIN:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        window = self.scrolled_window
        self.drag_origin = (
            window.get_hadjustment().get_value(),
            window.get_vadjustment().get_value(),
        )
        self.set_cursor_from_name("grabbing")

    def on_drag_update(self, gesture, offset_x, offset_y):
        origin_x, origin_y = self.drag_origin
        window = self.scrolled_window
        window.get_hadjustment().set_value(origin_x - offset_x)
        window.get_vadjustment().set_value(origin_y - offset_y)

    def on_drag_end(self, gesture, offset_x, offset_y):
        self.set_cursor(None)
