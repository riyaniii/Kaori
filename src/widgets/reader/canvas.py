import asyncio
import bisect
import math

from gi.repository import Adw, Gdk, Gio, Graphene, GObject, Gsk, Gtk

from .base import ZOOM_MAX

ZOOM_MIN = 0.5
PRELOAD = 1.0
IMAGE_PREFETCH = 4
POOL_MAX = 8


class Panel(Gtk.Stack):
    __gtype_name__ = "KaoriPanel"

    def __init__(self):
        super().__init__()
        self.ratio_handler = 0
        self.bindings = GObject.BindingGroup()
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.FILL)
        self.banner_title = Gtk.Label(
            css_classes=["title-1"],
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        spinner = Adw.Spinner(
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            width_request=48,
            height_request=48,
        )

        self.add_named(self.picture, "picture")
        self.add_named(spinner, "spinner")
        self.add_named(self.banner_title, "banner")
        self.set_visible_child_name("spinner")

        self.bindings.bind("paintable", self, "paintable", GObject.BindingFlags.SYNC_CREATE)

    @GObject.Property(type=Gdk.Paintable)
    def paintable(self):
        return self.picture.get_paintable()

    @paintable.setter
    def paintable(self, value):
        self.picture.set_paintable(value)
        self.set_visible_child_name("picture" if value else "spinner")

    def show_page(self, page):
        chapter = getattr(page, "chapter", None)
        if chapter is None:
            self.bindings.set_source(page)
        else:
            self.banner_title.set_label(chapter.name)
            self.set_visible_child_name("banner")

    def clear(self):
        self.bindings.set_source(None)
        self.paintable = None


class Canvas(Gtk.Widget, Gtk.Scrollable):
    __gtype_name__ = "KaoriCanvas"

    orientation = GObject.Property(type=Gtk.Orientation, default=Gtk.Orientation.VERTICAL)
    hadjustment = GObject.Property(type=Gtk.Adjustment)
    vadjustment = GObject.Property(type=Gtk.Adjustment)
    hscroll_policy = GObject.Property(type=Gtk.ScrollablePolicy, default=Gtk.ScrollablePolicy.NATURAL)
    vscroll_policy = GObject.Property(type=Gtk.ScrollablePolicy, default=Gtk.ScrollablePolicy.NATURAL)

    @GObject.Signal(arg_types=(int,))
    def page_changed(self, index):
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.store = None

        self.pages = []
        self.indices = {}
        self.starts = []
        self.sizes = []
        self.extent = 0.0
        self.cross = 0
        self.layout_dirty = False
        self.saved_anchor = None

        self.zoom = 1.0

        self.realized = {}
        self.tasks = {}
        self.pool = []
        self.current_page = None
        self.pending_index = None

        self.connect("notify::orientation", self.on_orientation_changed)
        self.connect("notify::hadjustment", self.on_adjustment_replaced)
        self.connect("notify::vadjustment", self.on_adjustment_replaced)

    def do_dispose(self):
        for page, panel in self.realized.items():
            page.disconnect(panel.ratio_handler)
        for task in self.tasks.values():
            task.cancel()
        while child := self.get_first_child():
            child.unparent()
        super().do_dispose()

    @GObject.Property(type=Gtk.TextDirection, default=Gtk.TextDirection.LTR)
    def direction(self):
        return self.get_direction()

    @direction.setter
    def direction(self, value):
        left = self.scroll_value(self.hadjustment) if self.hadjustment else 0
        self.set_direction(value)
        if self.hadjustment:
            self.set_scroll_value(self.hadjustment, left)
        self.queue_allocate()

    @property
    def vertical(self):
        return self.orientation == Gtk.Orientation.VERTICAL

    @property
    def mirrored(self):
        return not self.vertical and self.get_direction() == Gtk.TextDirection.RTL

    @property
    def main_adjustment(self):
        return self.vadjustment if self.vertical else self.hadjustment

    @property
    def content_width(self):
        return self.cross if self.vertical else self.extent

    @property
    def content_height(self):
        return self.extent if self.vertical else self.cross

    def scroll_value(self, adjustment):
        value = adjustment.get_value()
        if adjustment is self.hadjustment and self.mirrored:
            return adjustment.get_upper() - adjustment.get_page_size() - value
        return value

    def set_scroll_value(self, adjustment, value):
        if adjustment is self.hadjustment and self.mirrored:
            value = adjustment.get_upper() - adjustment.get_page_size() - value
        adjustment.set_value(value)

    def bind_store(self, store: Gio.ListStore):
        self.store = store
        store.connect("items-changed", self.on_items_changed)

    def on_items_changed(self, store, position, removed, added):
        self.invalidate_layout()
        self.pages = list(store)
        self.indices = {page: index for index, page in enumerate(self.pages)}
        for page in list(self.realized):
            if page not in self.indices:
                self.unrealize_panel(page)

    def on_ratio_changed(self, page, pspec):
        self.invalidate_layout()

    def invalidate_layout(self):
        if not self.layout_dirty:
            self.saved_anchor = self.find_anchor()
            self.layout_dirty = True
        self.queue_allocate()

    def index_at(self, position):
        return max(0, bisect.bisect_right(self.starts, position) - 1)

    def find_anchor(self):
        if not self.starts or self.cross == 0:
            return None
        top = self.scroll_value(self.main_adjustment) / self.zoom
        index = self.index_at(top)
        size = self.sizes[index]
        fraction = (top - self.starts[index]) / size if size else 0.0
        return self.pages[index], fraction

    def restore_anchor(self, anchor):
        if anchor is None:
            return
        page, fraction = anchor
        index = self.indices.get(page)
        if index is None:
            self.set_scroll_value(self.hadjustment, 0)
            self.set_scroll_value(self.vadjustment, 0)
            return
        position = self.starts[index] + fraction * self.sizes[index]
        self.set_scroll_value(self.main_adjustment, position * self.zoom)

    def scroll_to_index(self, index: int):
        if self.cross == 0 or self.layout_dirty:
            self.pending_index = index
            return
        self.pending_index = None
        if 0 <= index < len(self.starts):
            self.set_scroll_value(self.main_adjustment, self.starts[index] * self.zoom)

    def scroll_by(self, amount):
        adjustment = self.main_adjustment
        self.set_scroll_value(adjustment, self.scroll_value(adjustment) + amount)

    def scroll_page(self, direction):
        self.scroll_by(direction * self.main_adjustment.get_page_increment())

    def on_orientation_changed(self, canvas, pspec):
        if self.cross == 0:
            return
        self.pending_index = self.indices.get(self.current_page, 0)
        self.cross = 0
        self.set_scroll_value(self.hadjustment, 0)
        self.set_scroll_value(self.vadjustment, 0)
        self.queue_allocate()

    def relayout(self):
        self.starts = []
        self.sizes = []
        position = 0.0
        for page in self.pages:
            ratio = page.ratio
            size = self.cross / ratio if self.vertical else self.cross * ratio
            self.starts.append(position)
            self.sizes.append(size)
            position += size
        self.extent = position

    def visible_range(self):
        if not self.starts:
            return 0, -1
        adjustment = self.main_adjustment
        top = self.scroll_value(adjustment) / self.zoom
        size = adjustment.get_page_size() / self.zoom
        low = top - size * PRELOAD
        high = top + size * (1 + PRELOAD)
        first = max(0, bisect.bisect_right(self.starts, low) - 1)
        last = min(len(self.starts) - 1, bisect.bisect_left(self.starts, high))
        return first, last

    def update_current_page(self):
        if not self.starts:
            self.current_page = None
            return
        adjustment = self.main_adjustment
        middle = (self.scroll_value(adjustment) + adjustment.get_page_size() / 2) / self.zoom
        index = self.index_at(middle)
        page = self.pages[index]
        if page is not self.current_page:
            self.current_page = page
            self.emit("page-changed", index)

    def update_realized(self):
        first, last = self.visible_range()
        wanted = self.pages[first:last + 1]

        for page in list(self.realized):
            if page not in wanted:
                self.unrealize_panel(page)
        for page in wanted:
            if page not in self.realized:
                self.realize_panel(page)

        for page in self.pages[last + 1:last + 1 + IMAGE_PREFETCH]:
            self.suwayomi.prefetch(page.url)

    def realize_panel(self, page):
        if self.pool:
            panel = self.pool.pop()
            panel.set_visible(True)
        else:
            panel = Panel()
            panel.set_parent(self)

        panel.show_page(page)
        panel.ratio_handler = page.connect("notify::ratio", self.on_ratio_changed)
        self.realized[page] = panel

        if page.paintable is None and page.url:
            self.tasks[page] = asyncio.create_task(self.suwayomi.loadPage(page))

    def unrealize_panel(self, page):
        panel = self.realized.pop(page)
        page.disconnect(panel.ratio_handler)
        if task := self.tasks.pop(page, None):
            task.cancel()

        page.paintable = None
        panel.clear()
        panel.set_visible(False)
        if len(self.pool) < POOL_MAX:
            self.pool.append(panel)
        else:
            panel.unparent()

    def place_panels(self, width, height):
        left = self.scroll_value(self.hadjustment) / self.zoom
        top = self.scroll_value(self.vadjustment) / self.zoom

        offset_x = self.centering_offset(self.content_width, self.zoom, width)
        offset_y = self.centering_offset(self.content_height, self.zoom, height)

        for page, panel in self.realized.items():
            index = self.indices[page]
            x = offset_x - left
            y = offset_y - top
            if self.vertical:
                y += self.starts[index]
                panel_width, panel_height = self.cross, self.sizes[index]
            else:
                x += self.starts[index]
                panel_width, panel_height = self.sizes[index], self.cross
            if self.mirrored:
                x = width / self.zoom - x - panel_width

            transform = Gsk.Transform.new().translate(Graphene.Point().init(x, y))
            panel.allocate(math.ceil(panel_width), math.ceil(panel_height), -1, transform)

    def centering_offset(self, content_size, zoom, viewport_size):
        return max(0.0, (viewport_size / zoom - content_size) / 2)

    def anchored_scroll(self, adjustment, content_size, viewport_size, anchor, old_zoom, new_zoom):
        old_offset = self.centering_offset(content_size, old_zoom, viewport_size)
        new_offset = self.centering_offset(content_size, new_zoom, viewport_size)
        point = (self.scroll_value(adjustment) - old_offset * old_zoom + anchor) / old_zoom
        return point * new_zoom + new_offset * new_zoom - anchor

    def set_zoom_anchored(self, new_zoom, anchor_x, anchor_y):
        old_zoom = self.zoom
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, new_zoom))
        if abs(new_zoom - old_zoom) < 1e-6:
            return

        if self.mirrored:
            anchor_x = self.get_width() - anchor_x

        left = self.anchored_scroll(
            self.hadjustment, self.content_width, self.get_width(), anchor_x, old_zoom, new_zoom
        )
        top = self.anchored_scroll(
            self.vadjustment, self.content_height, self.get_height(), anchor_y, old_zoom, new_zoom
        )

        self.zoom = new_zoom
        self.configure_adjustments()
        self.set_scroll_value(self.hadjustment, left)
        self.set_scroll_value(self.vadjustment, top)
        self.queue_allocate()

    def scroll_fractions(self):
        return (
            self.fraction(self.hadjustment, self.content_width),
            self.fraction(self.vadjustment, self.content_height),
        )

    def fraction(self, adjustment, content_size):
        if content_size <= 0:
            return 0.0
        return self.scroll_value(adjustment) / self.zoom / content_size

    def restore_scroll_fractions(self, fractions):
        fraction_x, fraction_y = fractions
        self.configure_adjustments()
        self.set_scroll_value(self.hadjustment, fraction_x * self.content_width * self.zoom)
        self.set_scroll_value(self.vadjustment, fraction_y * self.content_height * self.zoom)

    def on_scrolled(self, adjustment):
        self.queue_allocate()

    def on_adjustment_replaced(self, canvas, pspec):
        if adjustment := self.get_property(pspec.name):
            adjustment.connect("value-changed", self.on_scrolled)
        self.configure_adjustments()

    def configure_adjustments(self):
        self.configure_adjustment(self.hadjustment, self.content_width, self.get_width(), self.mirrored)
        self.configure_adjustment(self.vadjustment, self.content_height, self.get_height(), False)

    def configure_adjustment(self, adjustment, content_size, viewport_size, flipped):
        if adjustment is None:
            return
        upper = max(content_size * self.zoom, viewport_size)
        if (
            abs(adjustment.get_upper() - upper) < 0.01
            and abs(adjustment.get_page_size() - viewport_size) < 0.01
        ):
            return
        value = adjustment.get_value()
        if flipped:
            old_end = adjustment.get_upper() - adjustment.get_page_size()
            value = upper - viewport_size - (old_end - value)
        adjustment.configure(value, 0.0, upper, 40.0, viewport_size * 0.9, viewport_size)

    def do_measure(self, orientation, for_size):
        return 0, 0, -1, -1

    def do_snapshot(self, snapshot):
        snapshot.scale(self.zoom, self.zoom)
        for panel in self.realized.values():
            self.snapshot_child(panel, snapshot)

    def do_size_allocate(self, width, height, baseline):
        cross = width if self.vertical else height
        if cross != self.cross:
            fractions = self.scroll_fractions()
            self.cross = cross
            self.relayout()
            self.restore_scroll_fractions(fractions)
        elif self.layout_dirty:
            self.relayout()
            self.configure_adjustments()
            self.restore_anchor(self.saved_anchor)
        self.layout_dirty = False
        self.saved_anchor = None
        self.configure_adjustments()

        if self.pending_index is not None:
            self.scroll_to_index(self.pending_index)

        self.update_current_page()
        self.update_realized()
        self.place_panels(width, height)
