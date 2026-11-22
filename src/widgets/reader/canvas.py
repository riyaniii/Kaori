import asyncio
import bisect
import math
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gio, Graphene, GObject, Gsk, Gtk

from .base import WEBTOON_ZOOM_MIN, ZOOM_MAX

PRELOAD = 1.0
LOAD_MARGIN = 2.0
UNLOAD_MARGIN = 3.0
IMAGE_PREFETCH = 4
POOL_MAX = 8
SNAP_EPSILON = 1e-3



def snap_outward(start, size):
    low = math.floor(start + SNAP_EPSILON)
    high = max(low + 1, math.ceil(start + size - SNAP_EPSILON))
    return low, high


def snap_to_device_pixels(value, device_scale):
    return round(value * device_scale) / device_scale

class Panel(Gtk.Stack):
    __gtype_name__ = "KaoriPanel"

    @GObject.Signal
    def retry_requested(self):
        pass

    def __init__(self):
        super().__init__()
        self.page = None
        self.failed_state = False
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

        error_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        error_box.append(Gtk.Image(icon_name="image-missing-symbolic", pixel_size=48))
        error_box.append(Gtk.Label(label=_("Couldn't load this page")))
        retry_button = Gtk.Button(label=_("Retry"), halign=Gtk.Align.CENTER, css_classes=["pill"])
        retry_button.connect("clicked", self.on_retry_clicked)
        error_box.append(retry_button)

        self.add_named(self.picture, "picture")
        self.add_named(spinner, "spinner")
        self.add_named(self.banner_title, "banner")
        self.add_named(error_box, "error")
        self.set_visible_child_name("spinner")

        self.bindings.bind("paintable", self, "paintable", GObject.BindingFlags.SYNC_CREATE)

    def on_retry_clicked(self, button):
        self.emit("retry-requested")

    def update_view(self):
        if self.failed_state:
            self.set_visible_child_name("error")
        elif self.picture.get_paintable() is not None:
            self.set_visible_child_name("picture")
        else:
            self.set_visible_child_name("spinner")

    @GObject.Property(type=Gdk.Paintable)
    def paintable(self):
        return self.picture.get_paintable()

    @paintable.setter
    def paintable(self, value):
        self.picture.set_paintable(value)
        self.update_view()

    @GObject.Property(type=bool, default=False)
    def failed(self):
        return self.failed_state

    @failed.setter
    def failed(self, value):
        self.failed_state = value
        self.update_view()

    def show_page(self, page):
        self.page = page
        chapter = getattr(page, "chapter", None)
        if chapter is None:
            self.bindings.set_source(page)
        else:
            self.banner_title.set_label(chapter.name)
            self.set_visible_child_name("banner")

    def clear(self):
        self.page = None
        self.bindings.set_source(None)
        self.failed = False
        self.paintable = None


class PanelLayer(Gtk.Widget):
    """Holds every realized panel in one local coordinate space.

    The canvas moves and scales this single widget when scrolling or zooming,
    so panels are only re-allocated when the layout or the realized set changes.
    GTK maps pointer picks through the layer's transform, so child widgets
    (the retry button) stay clickable at any scroll offset or zoom.
    """

    __gtype_name__ = "KaoriPanelLayer"

    def __init__(self):
        super().__init__()
        self.placements = {}

    def do_measure(self, orientation, for_size):
        return 0, 0, -1, -1

    def do_size_allocate(self, width, height, baseline):
        for panel, (x, y, panel_width, panel_height) in self.placements.items():
            transform = Gsk.Transform.new().translate(Graphene.Point().init(x, y))
            panel.allocate(panel_width, panel_height, -1, transform)

    def do_dispose(self):
        self.placements = {}
        while child := self.get_first_child():
            child.unparent()
        super().do_dispose()


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
        self.store_handler = 0

        self.pages = []
        self.indices = {}
        self.starts = []
        self.sizes = []
        self.layout_ratios = {}
        self.extent = 0.0
        self.cross = 0
        self.layout_dirty = False
        self.refresh_anchor = False
        self.saved_anchor = None
        self.window = None

        self.zoom = 1.0

        self.realized = {}
        self.tasks = {}
        self.failed_pages = set()
        self.ratio_handlers = {}
        self.pool = []
        self.current_page = None
        self.pending_index = None

        self.layer = PanelLayer()
        self.layer.set_parent(self)
        self.placements_dirty = False
        self.layer_origin = 0.0
        self.layer_end = 0.0
        self.layer_main = 0

        self.connect("notify::orientation", self.on_orientation_changed)
        self.connect("notify::hadjustment", self.on_adjustment_replaced)
        self.connect("notify::vadjustment", self.on_adjustment_replaced)

    def do_dispose(self):
        if self.store is not None and self.store_handler:
            self.store.disconnect(self.store_handler)
            self.store_handler = 0
        for page, handler in self.ratio_handlers.items():
            page.disconnect(handler)
        self.ratio_handlers.clear()
        for task in self.tasks.values():
            task.cancel()
        self.layer.placements = {}
        for panel in [*self.realized.values(), *self.pool]:
            panel.unparent()
        self.realized.clear()
        self.pool.clear()
        self.layer.unparent()
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
        self.placements_dirty = True
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
        self.store_handler = store.connect("items-changed", self.on_items_changed)

    def watch_page_ratios(self):
        for page in self.pages:
            if page not in self.ratio_handlers:
                self.ratio_handlers[page] = page.connect("notify::ratio", self.on_ratio_changed)
        for page in [page for page in self.ratio_handlers if page not in self.indices]:
            page.disconnect(self.ratio_handlers.pop(page))

    def on_items_changed(self, store, position, removed, added):
        self.invalidate_layout()
        self.window = None
        self.pages = list(store)
        self.indices = {page: index for index, page in enumerate(self.pages)}

        self.watch_page_ratios()

        for page in list(self.realized):
            if page not in self.indices:
                self.unrealize_panel(page)
        for page in list(self.tasks):
            if page not in self.indices:
                self.unload(page)

    def on_ratio_changed(self, page, pspec):
        if self.layout_ratios.get(page) == page.ratio:
            return
        if not self.layout_dirty:
            self.layout_dirty = True
            self.refresh_anchor = True
        self.queue_allocate()

    def invalidate_layout(self):
        if not self.layout_dirty or self.refresh_anchor:
            self.saved_anchor = self.find_anchor()
            self.refresh_anchor = False
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
        self.layout_ratios = {}
        self.window = None
        self.placements_dirty = True
        position = 0.0
        for page in self.pages:
            ratio = page.ratio
            size = self.cross / ratio if self.vertical else self.cross * ratio
            self.layout_ratios[page] = ratio
            self.starts.append(position)
            self.sizes.append(size)
            position += size
        self.extent = position

    def visible_range(self, margin):
        if not self.starts:
            return 0, -1
        adjustment = self.main_adjustment
        top = self.scroll_value(adjustment) / self.zoom
        size = adjustment.get_page_size() / self.zoom
        low = top - size * margin
        high = top + size * (1 + margin)
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
        window = (
            self.visible_range(PRELOAD),
            self.visible_range(LOAD_MARGIN),
            self.visible_range(UNLOAD_MARGIN),
        )
        if window == self.window:
            return
        self.window = window

        (first, last), (load_first, load_last), (keep_first, keep_last) = window
        visible = self.pages[first:last + 1]
        wanted = set(visible)

        for page in list(self.realized):
            if page not in wanted:
                self.unrealize_panel(page)
        for page in visible:
            if page not in self.realized:
                self.realize_panel(page)

        keep = set(self.pages[keep_first:keep_last + 1])

        for page in list(self.tasks):
            if page not in keep:
                self.unload(page)
        for page in self.pages[load_first:load_last + 1]:
            if page.url and page not in self.tasks:
                self.start_load(page)

        for page in self.pages[load_last + 1:load_last + 1 + IMAGE_PREFETCH]:
            self.suwayomi.prefetch(page.url)

    def realize_panel(self, page):
        if self.pool:
            panel = self.pool.pop()
            panel.set_visible(True)
        else:
            panel = Panel()
            panel.connect("retry-requested", self.on_retry_requested)
            panel.set_parent(self.layer)

        panel.show_page(page)
        panel.failed = page in self.failed_pages
        self.realized[page] = panel
        self.placements_dirty = True

    def unrealize_panel(self, page):
        panel = self.realized.pop(page)
        self.layer.placements.pop(panel, None)
        panel.clear()
        panel.set_visible(False)
        if len(self.pool) < POOL_MAX:
            self.pool.append(panel)
        else:
            panel.unparent()
        self.placements_dirty = True

    def start_load(self, page):
        old_task = self.tasks.pop(page, None)
        if old_task is not None:
            old_task.cancel()

        self.failed_pages.discard(page)
        panel = self.realized.get(page)
        if panel is not None:
            panel.failed = False

        task = asyncio.create_task(self.suwayomi.loadPage(page))
        self.tasks[page] = task
        task.add_done_callback(lambda done, page=page: self.on_load_done(page, done))

    def unload(self, page):
        self.tasks.pop(page).cancel()
        self.failed_pages.discard(page)
        page.paintable = None

    def on_load_done(self, page, task):
        if task.cancelled() or self.tasks.get(page) is not task:
            return
        if page.paintable is not None:
            return

        self.failed_pages.add(page)
        panel = self.realized.get(page)
        if panel is not None:
            panel.failed = True

    def on_retry_requested(self, panel):
        if panel.page is not None:
            self.start_load(panel.page)

    def retry_failed(self):
        for page in list(self.failed_pages):
            self.start_load(page)

    def update_placements(self):
        """Lay realized panels out inside the layer. Runs only when the layout
        or the realized set changed, never on a plain scroll tick."""
        self.placements_dirty = False
        slots = {page: self.indices[page] for page in self.realized}
        if not slots:
            self.layer.placements = {}
            return

        origin = min(self.starts[index] for index in slots.values())
        end = max(self.starts[index] + self.sizes[index] for index in slots.values())
        cross = math.ceil(self.cross)

        placements = {}
        main = 1
        for page, panel in self.realized.items():
            index = slots[page]
            start, size = self.starts[index], self.sizes[index]
            local = end - start - size if self.mirrored else start - origin
            low, high = snap_outward(local, size)
            main = max(main, high)
            if self.vertical:
                placements[panel] = (0, low, cross, high - low)
            else:
                placements[panel] = (low, 0, high - low, cross)

        self.layer_origin = origin
        self.layer_end = end
        self.layer_main = main
        self.layer.placements = placements
        self.layer.queue_allocate()

    def place_panels(self, width, height):
        if self.placements_dirty:
            self.update_placements()
        if not self.realized:
            return

        zoom = self.zoom
        scroll_x = self.scroll_value(self.hadjustment)
        scroll_y = self.scroll_value(self.vadjustment)
        offset_x = self.centering_offset(self.content_width, zoom, width)
        offset_y = self.centering_offset(self.content_height, zoom, height)

        if self.vertical:
            x = zoom * offset_x - scroll_x
            y = zoom * (offset_y + self.layer_origin) - scroll_y
            layer_width, layer_height = math.ceil(self.cross), self.layer_main
        else:
            if self.mirrored:
                x = width - zoom * offset_x + scroll_x - zoom * self.layer_end
            else:
                x = zoom * (offset_x + self.layer_origin) - scroll_x
            y = zoom * offset_y - scroll_y
            layer_width, layer_height = self.layer_main, math.ceil(self.cross)

        device_scale = self.get_scale_factor()
        x = snap_to_device_pixels(x, device_scale)
        y = snap_to_device_pixels(y, device_scale)

        transform = Gsk.Transform.new().translate(Graphene.Point().init(x, y))
        if zoom != 1.0:
            transform = transform.scale(zoom, zoom)
        self.layer.allocate(layer_width, layer_height, -1, transform)

    def centering_offset(self, content_size, zoom, viewport_size):
        return max(0.0, (viewport_size / zoom - content_size) / 2)

    def anchored_scroll(self, adjustment, content_size, viewport_size, anchor, old_zoom, new_zoom):
        old_offset = self.centering_offset(content_size, old_zoom, viewport_size)
        new_offset = self.centering_offset(content_size, new_zoom, viewport_size)
        point = (self.scroll_value(adjustment) - old_offset * old_zoom + anchor) / old_zoom
        return point * new_zoom + new_offset * new_zoom - anchor

    def set_zoom_anchored(self, new_zoom, anchor_x, anchor_y):
        old_zoom = self.zoom
        new_zoom = max(WEBTOON_ZOOM_MIN, min(ZOOM_MAX, new_zoom))
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

    def do_size_allocate(self, width, height, baseline):
        cross = width if self.vertical else height
        if cross != self.cross:
            fractions = self.scroll_fractions()
            self.cross = cross
            self.relayout()
            self.restore_scroll_fractions(fractions)
        elif self.layout_dirty:
            anchor = self.find_anchor() if self.refresh_anchor else self.saved_anchor
            self.relayout()
            self.configure_adjustments()
            self.restore_anchor(anchor)
        self.layout_dirty = False
        self.refresh_anchor = False
        self.saved_anchor = None
        self.configure_adjustments()

        if self.pending_index is not None:
            self.scroll_to_index(self.pending_index)

        self.update_current_page()
        self.update_realized()
        self.place_panels(width, height)
        self.queue_draw()
