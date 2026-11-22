import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango

from .row import DownloadRow


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/download/page.ui')
class DownloadsPage(Adw.NavigationPage):
    __gtype_name__ = "KaoriDownloadsPage"

    downloads = GObject.Property(type=Gio.ListStore)
    downloader_state = GObject.Property(type=str)

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.poll_id = 0

        self.downloads = self.suwayomi.download_queue
        self.suwayomi.bind_property(
            "downloader-state", self, "downloader-state", GObject.BindingFlags.SYNC_CREATE,
        )
        self.connect("map", self.on_map)
        self.connect("unmap", self.on_unmap)

    def on_map(self, page):
        asyncio.create_task(self.suwayomi.getDownloadStatus())
        self.poll_id = GLib.timeout_add_seconds(1, self.on_poll)

    def on_unmap(self, page):
        if self.poll_id:
            GLib.source_remove(self.poll_id)
            self.poll_id = 0

    def on_poll(self):
        asyncio.create_task(self.suwayomi.getDownloadStatus())
        return GLib.SOURCE_CONTINUE

    @Gtk.Template.Callback()
    def get_page(self, obj, count):
        return "downloads" if count > 0 else "greeter"

    @Gtk.Template.Callback()
    def get_toggle_icon(self, obj, state):
        if state == "STARTED":
            return "media-playback-pause-symbolic"
        return "media-playback-start-symbolic"

    @Gtk.Template.Callback()
    def get_toggle_tooltip(self, obj, state):
        if state == "STARTED":
            return _("Pause downloads")
        return _("Start downloads")

    @Gtk.Template.Callback()
    def on_setup(self, factory, list_item):
        list_item.set_selectable(False)
        list_item.set_activatable(False)
        row = DownloadRow()
        row.connect("reorder-requested", self.on_reorder_requested)
        row.connect("remove-requested", self.on_remove_requested)
        row.connect("retry-requested", self.on_retry_requested)
        list_item.set_child(row)

    @Gtk.Template.Callback()
    def on_bind(self, factory, list_item):
        list_item.get_child().model = list_item.get_item()

    @Gtk.Template.Callback()
    def on_unbind(self, factory, list_item):
        list_item.get_child().model = None

    @Gtk.Template.Callback()
    def on_header_setup(self, factory, header):
        header.set_child(Gtk.Label(
            xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["title-4"],
            margin_top=18, margin_bottom=6, margin_start=6, margin_end=6,
        ))
        header.connect("notify::item", self.update_header)

    @Gtk.Template.Callback()
    def on_header_bind(self, factory, header):
        self.update_header(header)

    def update_header(self, header, *args):
        item = header.get_item()
        header.get_child().set_label(item.manga_title if item else "")

    def on_reorder_requested(self, row, dragged_chapter_id, target_chapter_id):
        for index, download in enumerate(self.suwayomi.download_queue):
            if download.chapter_id == target_chapter_id:
                asyncio.create_task(
                    self.suwayomi.reorderChapterDownload(dragged_chapter_id, index)
                )
                return

    def on_remove_requested(self, row, chapter_id):
        asyncio.create_task(self.suwayomi.dequeueChapterDownload(chapter_id))

    def on_retry_requested(self, row, chapter_id):
        asyncio.create_task(self.retry(chapter_id))

    async def retry(self, chapter_id):
        await self.suwayomi.dequeueChapterDownload(chapter_id)
        await self.suwayomi.enqueueChapterDownload(chapter_id)

    @Gtk.Template.Callback()
    def on_toggle_clicked(self, *args):
        if self.downloader_state == "STARTED":
            asyncio.create_task(self.suwayomi.stopDownloader())
        else:
            asyncio.create_task(self.suwayomi.startDownloader())

    @Gtk.Template.Callback()
    def on_clear_clicked(self, *args):
        dialog = Adw.AlertDialog(
            heading=_("Clear download queue?"),
            body=_("Every queued chapter will be removed. Chapters already downloaded stay on the server."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("clear", _("Clear"))
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self.on_clear_response)
        dialog.present(self)

    def on_clear_response(self, dialog, response):
        if response == "clear":
            asyncio.create_task(self.suwayomi.clearDownloader())
