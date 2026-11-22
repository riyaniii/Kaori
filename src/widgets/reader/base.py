import asyncio
import math
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from ...integrations import models

ZOOM_MIN = 1.0
WEBTOON_ZOOM_MIN = 0.5
ZOOM_MAX = 4.0
ZOOM_STEP = 1.25
ZOOM_ANIMATION_TIME = 150
FADE_TIME = 120
PIXELS_PER_STEP = 40
PREFETCH_SPREADS = 2
DRAG_THRESHOLD = 4
LAST_PAGE = 10**6


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

    zoom_min = ZOOM_MIN

    chapter_model = GObject.Property(type=models.Chapter)
    manga_model = GObject.Property(type=models.Manga)

    @GObject.Signal(arg_types=(int,))
    def chapter_requested(self, direction):
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.store = None
        self.pointer = (0.0, 0.0)
        self.pinch_start = 1.0
        self.zoom_animation = None
        self.zoom_goal = 1.0

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
    def step(self):
        return 1

    @property
    def page_count(self):
        if self.chapter_model:
            return self.chapter_model.page_count
        return 0

    @property
    def zoom_basis(self):
        animation = self.zoom_animation
        if animation is not None and animation.get_state() == Adw.AnimationState.PLAYING:
            return self.zoom_goal
        return self.zoom

    def bind_store(self, store: Gio.ListStore):
        self.store = store

    def show_toast(self, message):
        self.activate_action("app.show_toast", GLib.Variant("s", message))

    def retry_failed(self):
        pass

    def next_page(self):
        self.position += 1

    def previous_page(self):
        self.position -= 1

    def zoom_to(self, value, x, y):
        raise NotImplementedError

    def stop_zoom_animation(self):
        if self.zoom_animation is not None:
            self.zoom_animation.pause()
            self.zoom_animation = None

    def animate_zoom(self, value, x, y):
        value = max(self.zoom_min, min(ZOOM_MAX, value))
        self.stop_zoom_animation()
        self.zoom_goal = value
        target = Adw.CallbackAnimationTarget.new(lambda current: self.zoom_to(current, x, y))
        self.zoom_animation = Adw.TimedAnimation.new(
            self, self.zoom, value, ZOOM_ANIMATION_TIME, target
        )
        self.zoom_animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.zoom_animation.play()

    def zoom_by(self, factor):
        center_x = self.get_width() / 2
        center_y = self.get_height() / 2
        self.animate_zoom(self.zoom_basis * factor, center_x, center_y)

    def zoom_in(self):
        self.zoom_by(ZOOM_STEP)

    def zoom_out(self):
        self.zoom_by(1 / ZOOM_STEP)

    def reset_zoom(self):
        self.animate_zoom(1.0, self.get_width() / 2, self.get_height() / 2)

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
        self.animate_zoom(self.zoom_basis * ZOOM_STEP ** -steps, pointer_x, pointer_y)
        return Gdk.EVENT_STOP

    def on_pinch_begin(self, gesture, sequence):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.stop_zoom_animation()
        self.pinch_start = self.zoom

    def on_pinch_scale_changed(self, gesture, scale):
        found, x, y = gesture.get_bounding_box_center()
        if found:
            self.zoom_to(self.pinch_start * scale, x, y)

    def on_double_tap(self, gesture, n_press, x, y):
        if n_press == 2:
            self.animate_zoom(1.0, x, y)


class PagedReader(ReaderBase):
    __gtype_name__ = "KaoriPagedReader"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.zoom = 1.0
        self.current_position = 0
        self.tasks = {}
        self.failed_pages = set()
        self.groups = {}
        self.drag_last = (0.0, 0.0)
        self.drag_moved = False
        self.fade = None

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

    def fade_in(self):
        if self.fade is not None:
            self.fade.pause()
        self.content.set_opacity(0.0)
        target = Adw.CallbackAnimationTarget.new(self.content.set_opacity)
        self.fade = Adw.TimedAnimation.new(self, 0.0, 1.0, FADE_TIME, target)
        self.fade.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.fade.play()

    def show_current(self):
        if self.store is None or not self.get_mapped():
            return

        self.stop_zoom_animation()
        self.zoom_to(1.0, self.get_width() / 2, self.get_height() / 2)
        for offset, picture in enumerate(self.pictures):
            page = self.page_at(self.current_position + offset)
            picture.set_paintable(None)
            self.binding_group(picture).set_source(page)
        self.refresh_window()
        self.fade_in()

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
        self.failed_pages.discard(page)
        task = asyncio.create_task(self.suwayomi.loadPage(page))
        self.tasks[page] = task
        task.add_done_callback(lambda done, page=page: self.on_load_done(page, done))

    def on_load_done(self, page, task):
        if self.tasks.get(page) is task:
            del self.tasks[page]
        if task.cancelled() or page.paintable is not None:
            return

        self.failed_pages.add(page)
        if self.current_position <= page.index < self.current_position + self.step:
            self.show_toast(_("Couldn't load page {}. Press R to retry").format(page.index + 1))

    def retry_failed(self):
        for page in self.wanted_pages():
            if page in self.failed_pages and page not in self.tasks:
                self.start_load(page)

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

        self.drag_moved = False
        self.drag_last = (0.0, 0.0)

    def on_drag_update(self, gesture, offset_x, offset_y):
        if not self.drag_moved:
            if math.hypot(offset_x, offset_y) < DRAG_THRESHOLD:
                return
            self.drag_moved = True
            self.stop_zoom_animation()
            self.set_cursor_from_name("grabbing")
            self.drag_last = (offset_x, offset_y)
            return

        last_x, last_y = self.drag_last
        window = self.scrolled_window
        hadjustment = window.get_hadjustment()
        vadjustment = window.get_vadjustment()
        hadjustment.set_value(hadjustment.get_value() - (offset_x - last_x))
        vadjustment.set_value(vadjustment.get_value() - (offset_y - last_y))
        self.drag_last = (offset_x, offset_y)

    def on_drag_end(self, gesture, offset_x, offset_y):
        self.drag_moved = False
        self.set_cursor(None)
