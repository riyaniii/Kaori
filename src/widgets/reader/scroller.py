import math

from gi.repository import Gdk, GLib, Gtk

SCROLL_SPEED = 800
SCROLL_ACCEL_TIME = 0.08
SCROLL_DECEL_TIME = 0.18
SCROLL_STOP_SPEED = 5
MAX_FRAME_DELTA = 0.05
NOMINAL_FRAME = 1 / 60
PAGE_SCROLL_RATIO = 0.9
FLING_DECEL_TIME = 0.35
FLING_MIN_SPEED = 200
FLING_MAX_SPEED = 6000
FLING_IDLE_TIME = 0.08
WHEEL_DISTANCE = 110
WHEEL_DECEL_TIME = 0.2
DRAG_THRESHOLD = 4


class Scroller:
    def __init__(self, webtoon):
        self.webtoon = webtoon
        self.canvas = webtoon.canvas

        self.key_direction = 0
        self.velocity = 0.0
        self.decel_time = SCROLL_DECEL_TIME
        self.tick_id = 0
        self.last_frame_time = None

        self.dragging = False
        self.moved = False
        self.last_x = 0.0
        self.last_y = 0.0
        self.drag_velocity = 0.0
        self.last_time = 0.0
        self.last_offset = 0.0

        drag = Gtk.GestureDrag(button=1)
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        webtoon.add_controller(drag)
        webtoon.set_cursor_from_name("grab")

    def now(self):
        return GLib.get_monotonic_time() / GLib.USEC_PER_SEC

    def current_target(self):
        if self.key_direction:
            return self.key_direction * SCROLL_SPEED, SCROLL_ACCEL_TIME
        return 0.0, self.decel_time

    def ensure_ticking(self):
        if self.tick_id:
            return
        self.last_frame_time = None
        self.tick_id = self.webtoon.add_tick_callback(self.on_tick)

    def on_tick(self, widget, frame_clock):
        frame_time = frame_clock.get_frame_time()
        if self.last_frame_time is None:
            elapsed = NOMINAL_FRAME
        else:
            elapsed = (frame_time - self.last_frame_time) / GLib.USEC_PER_SEC
        self.last_frame_time = frame_time
        elapsed = min(max(elapsed, 0.0), MAX_FRAME_DELTA)

        if not self.webtoon.get_mapped():
            self.stop_all()
            self.tick_id = 0
            return GLib.SOURCE_REMOVE

        target, tau = self.current_target()
        self.velocity += (target - self.velocity) * (1 - math.exp(-elapsed / tau))

        if target == 0 and abs(self.velocity) < SCROLL_STOP_SPEED:
            self.velocity = 0.0
            self.tick_id = 0
            return GLib.SOURCE_REMOVE

        self.canvas.scroll_by(self.velocity * elapsed)
        return GLib.SOURCE_CONTINUE

    def start_keys(self, direction):
        if direction != self.key_direction:
            self.webtoon.cancel_kinetic()
        self.decel_time = SCROLL_DECEL_TIME
        self.key_direction = direction
        self.ensure_ticking()

    def stop_keys(self):
        self.key_direction = 0

    def stop_all(self):
        self.key_direction = 0
        self.velocity = 0.0

    def fling(self, velocity, decel_time=FLING_DECEL_TIME):
        self.velocity = velocity
        self.decel_time = decel_time
        self.ensure_ticking()

    def wheel(self, steps):
        self.key_direction = 0
        if not self.tick_id:
            self.webtoon.cancel_kinetic()
        impulse = steps * WHEEL_DISTANCE / WHEEL_DECEL_TIME
        velocity = self.velocity + impulse
        velocity = max(-FLING_MAX_SPEED, min(FLING_MAX_SPEED, velocity))
        self.fling(velocity, WHEEL_DECEL_TIME)

    def scroll_page(self, direction):
        self.key_direction = 0
        self.webtoon.cancel_kinetic()
        horizontal = self.webtoon.orientation == Gtk.Orientation.HORIZONTAL
        size = self.canvas.get_width() if horizontal else self.canvas.get_height()
        distance = direction * size * PAGE_SCROLL_RATIO
        self.fling(distance / SCROLL_DECEL_TIME, SCROLL_DECEL_TIME)

    def on_drag_begin(self, gesture, x, y):
        source = gesture.get_device().get_source()
        if source == Gdk.InputSource.TOUCHSCREEN:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            self.dragging = False
            return

        self.dragging = True
        self.moved = False
        self.last_x = 0.0
        self.last_y = 0.0
        self.drag_velocity = 0.0
        self.last_time = self.now()
        self.last_offset = 0.0

    def on_drag_update(self, gesture, offset_x, offset_y):
        if not self.dragging:
            return

        if not self.moved:
            if math.hypot(offset_x, offset_y) < DRAG_THRESHOLD:
                return
            self.moved = True
            self.stop_all()
            self.webtoon.cancel_kinetic()
            self.webtoon.set_cursor_from_name("grabbing")
            self.last_x, self.last_y = offset_x, offset_y
            self.last_offset = offset_y if self.canvas.vertical else offset_x
            self.last_time = self.now()
            return

        hadjustment = self.canvas.hadjustment
        vadjustment = self.canvas.vadjustment
        hadjustment.set_value(hadjustment.get_value() - (offset_x - self.last_x))
        vadjustment.set_value(vadjustment.get_value() - (offset_y - self.last_y))
        self.last_x, self.last_y = offset_x, offset_y

        now = self.now()
        elapsed = now - self.last_time
        if elapsed < 0.001:
            return

        offset = offset_y if self.canvas.vertical else offset_x
        sample = -(offset - self.last_offset) / elapsed
        self.drag_velocity = self.drag_velocity * 0.6 + sample * 0.4
        self.last_time = now
        self.last_offset = offset

    def on_drag_end(self, gesture, offset_x, offset_y):
        if not self.dragging:
            return

        self.dragging = False
        self.webtoon.set_cursor_from_name("grab")
        if not self.moved:
            return

        velocity = -self.drag_velocity if self.canvas.mirrored else self.drag_velocity
        velocity = max(-FLING_MAX_SPEED, min(FLING_MAX_SPEED, velocity))

        resting = self.now() - self.last_time > FLING_IDLE_TIME
        if resting or abs(velocity) < FLING_MIN_SPEED:
            return
        self.fling(velocity)
