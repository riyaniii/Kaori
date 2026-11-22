import asyncio

from gi.repository import GLib, Gtk

SETTINGS_SAVE_DELAY = 500

ORIENTATIONS = {
    "vertical": Gtk.Orientation.VERTICAL,
    "horizontal": Gtk.Orientation.HORIZONTAL,
}
DIRECTIONS = {
    "ltr": Gtk.TextDirection.LTR,
    "rtl": Gtk.TextDirection.RTL,
}


class ReaderSettings:
    def __init__(self, page):
        self.page = page
        self.suwayomi = page.suwayomi
        self.applying = False
        self.loaded = False
        self.save_id = 0

        page.connect("notify::direction", self.on_changed)
        page.webtoon.connect("notify::orientation", self.on_changed)
        self.task = asyncio.create_task(self.load())

    async def load(self):
        try:
            settings = await self.suwayomi.getReaderSettings(self.page.manga_model.id)
        except Exception:
            settings = {}
        self.apply(settings or {})
        self.loaded = True

    def apply(self, settings):
        page = self.page
        self.applying = True
        try:
            if settings.get("mode") in page.readers:
                page.stack.set_visible_child_name(settings["mode"])
            if settings.get("orientation") in ORIENTATIONS:
                page.webtoon.orientation = ORIENTATIONS[settings["orientation"]]
            if settings.get("direction") in DIRECTIONS:
                page.direction = DIRECTIONS[settings["direction"]]
        finally:
            self.applying = False

    def current(self):
        page = self.page
        return {
            "mode": page.stack.get_visible_child_name(),
            "orientation": page.webtoon.orientation.value_nick,
            "direction": page.direction.value_nick,
        }

    def on_changed(self, *args):
        if self.applying or not self.loaded:
            return
        if self.save_id:
            GLib.source_remove(self.save_id)
        self.save_id = GLib.timeout_add(SETTINGS_SAVE_DELAY, self.flush)

    def flush(self):
        self.save_id = 0
        asyncio.create_task(
            self.suwayomi.setReaderSettings(self.page.manga_model.id, self.current())
        )
        return GLib.SOURCE_REMOVE

    def finish(self):
        self.task.cancel()
        if self.save_id:
            GLib.source_remove(self.save_id)
            self.flush()
