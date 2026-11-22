import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk


def score_index(tracker, record):
    scores = tracker["scores"]
    if record["displayScore"] in scores:
        return scores.index(record["displayScore"])
    return 0


def status_index(tracker, record):
    for index, status in enumerate(tracker["statuses"]):
        if status["value"] == record["status"]:
            return index
    return 0


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/manga/tracking.ui')
class TrackingDialog(Adw.Dialog):
    __gtype_name__ = "KaoriTrackingDialog"

    navigation = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    trackers_page = Gtk.Template.Child()
    search_page = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    search_stack = Gtk.Template.Child()
    results_group = Gtk.Template.Child()

    def __init__(self, manga):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.manga = manga
        self.groups = []
        self.result_rows = []
        self.search_tracker = None
        asyncio.create_task(self.load())

    def show_toast(self, message):
        Gio.Application.get_default().activate_action("show_toast", GLib.Variant("s", message))

    async def load(self):
        self.stack.set_visible_child_name("loading")
        try:
            records, trackers = await self.suwayomi.getMangaTracking(self.manga.id)
        except Exception as error:
            print("Loading tracking failed:", error)
            self.show_toast(_("Couldn't load tracking"))
            if self.get_root() is not None:
                self.force_close()
            return

        for group in self.groups:
            self.trackers_page.remove(group)
        self.groups = []

        untracked = []
        for tracker in trackers:
            record = self.record_for(tracker, records)
            if record:
                self.add_tracked_group(tracker, record)
            else:
                untracked.append(tracker)
        if untracked:
            self.add_untracked_group(untracked)

        self.stack.set_visible_child_name("trackers" if trackers else "empty")

    def record_for(self, tracker, records):
        for record in records:
            if record["trackerId"] == tracker["id"]:
                return record
        return None

    def add_group(self, **properties):
        group = Adw.PreferencesGroup(**properties)
        self.trackers_page.add(group)
        self.groups.append(group)
        return group

    def make_logo(self, url, width, height):
        picture = Gtk.Picture(
            content_fit=Gtk.ContentFit.COVER,
            width_request=width,
            height_request=height,
            valign=Gtk.Align.CENTER,
            overflow=Gtk.Overflow.HIDDEN,
            css_classes=["r5"],
        )
        if url:
            asyncio.create_task(self.load_picture(picture, url))
        else:
            picture.set_visible(False)
        return picture

    async def load_picture(self, picture, url):
        try:
            picture.set_paintable(await self.suwayomi.getPaintable(url))
        except Exception as error:
            print("Tracking image failed:", error)

    def add_untracked_group(self, trackers):
        group = self.add_group(
            title=_("Not Tracked"),
            description=_("Link this manga to keep your progress in sync"),
        )
        for tracker in trackers:
            row = Adw.ActionRow(title=GLib.markup_escape_text(tracker["name"]))
            row.add_prefix(self.make_logo(self.suwayomi.trackerIconUrl(tracker), 32, 32))
            button = Gtk.Button(label=_("Track"), valign=Gtk.Align.CENTER)
            button.connect("clicked", self.on_start_tracking, tracker)
            row.add_suffix(button)
            row.set_activatable_widget(button)
            group.add(row)

    def add_tracked_group(self, tracker, record):
        stop_button = Gtk.Button(label=_("Stop Tracking"), valign=Gtk.Align.CENTER, css_classes=["flat"])
        stop_button.connect("clicked", self.on_stop_tracking, record)
        group = self.add_group(title=GLib.markup_escape_text(tracker["name"]), header_suffix=stop_button)

        title_row = Adw.ActionRow(
            title=GLib.markup_escape_text(record["title"]),
            subtitle=_("Open on {}").format(GLib.markup_escape_text(tracker["name"])),
            activatable=bool(record["remoteUrl"]),
        )
        title_row.add_prefix(self.make_logo(self.suwayomi.trackerIconUrl(tracker), 32, 32))
        title_row.add_suffix(Gtk.Image(icon_name="adw-external-link-symbolic"))
        title_row.connect("activated", self.on_open_remote, record)
        group.add(title_row)

        status_names = Gtk.StringList()
        for status in tracker["statuses"]:
            status_names.append(status["name"])
        status_row = Adw.ComboRow(title=_("Status"), model=status_names)
        status_row.set_selected(status_index(tracker, record))
        status_row.connect("notify::selected", self.on_status_changed, tracker, record)
        group.add(status_row)

        upper = record["totalChapters"] or 10000
        chapter_row = Adw.SpinRow.new_with_range(0, upper, 1)
        chapter_row.set_title(_("Chapters Read"))
        if record["totalChapters"]:
            chapter_row.set_subtitle(_("Out of {}").format(record["totalChapters"]))
        chapter_row.set_value(record["lastChapterRead"])
        chapter_row.connect("notify::value", self.on_chapter_changed, record)
        group.add(chapter_row)

        score_row = Adw.ComboRow(title=_("Score"), model=Gtk.StringList.new(tracker["scores"]))
        score_row.set_selected(score_index(tracker, record))
        score_row.connect("notify::selected", self.on_score_changed, tracker, record)
        group.add(score_row)

        if tracker["supportsPrivateTracking"]:
            private_row = Adw.SwitchRow(
                title=_("Private"),
                subtitle=_("Hide this entry from your public profile"),
                active=record["private"],
            )
            private_row.connect("notify::active", self.on_private_changed, record)
            group.add(private_row)

    def on_open_remote(self, row, record):
        Gtk.UriLauncher(uri=record["remoteUrl"]).launch(self.get_root(), None, None)

    def change(self, record, **changes):
        asyncio.create_task(self.save_change(record, changes))

    async def save_change(self, record, changes):
        try:
            await self.suwayomi.updateTrack(record["id"], **changes)
        except Exception as error:
            print("Updating the tracker failed:", error)
            self.show_toast(_("Couldn't update the tracker"))

    def on_status_changed(self, row, pspec, tracker, record):
        self.change(record, status=tracker["statuses"][row.get_selected()]["value"])

    def on_chapter_changed(self, row, pspec, record):
        self.change(record, last_chapter_read=row.get_value())

    def on_score_changed(self, row, pspec, tracker, record):
        self.change(record, score=tracker["scores"][row.get_selected()])

    def on_private_changed(self, row, pspec, record):
        self.change(record, private=row.get_active())

    def on_stop_tracking(self, button, record):
        asyncio.create_task(self.stop_tracking(record))

    async def stop_tracking(self, record):
        try:
            await self.suwayomi.unbindTrack(record["id"])
        except Exception as error:
            print("Stopping tracking failed:", error)
            self.show_toast(_("Couldn't stop tracking"))
        await self.load()

    def on_start_tracking(self, button, tracker):
        self.search_tracker = tracker
        self.search_page.set_title(_("Find on {}").format(tracker["name"]))
        self.search_entry.set_text(self.manga.title)
        self.navigation.push(self.search_page)
        self.search()

    @Gtk.Template.Callback()
    def on_search_activate(self, entry):
        self.search()

    def search(self):
        text = self.search_entry.get_text().strip()
        if text and self.search_tracker:
            asyncio.create_task(self.load_results(self.search_tracker, text))

    async def load_results(self, tracker, text):
        self.search_stack.set_visible_child_name("loading")
        try:
            results = await self.suwayomi.searchTracker(tracker["id"], text)
        except Exception as error:
            print("Tracker search failed:", error)
            results = []

        for row in self.result_rows:
            self.results_group.remove(row)
        self.result_rows = []

        for result in results:
            self.add_result_row(tracker, result)

        self.search_stack.set_visible_child_name("results" if results else "empty")

    def add_result_row(self, tracker, result):
        details = []
        if result["publishingType"]:
            details.append(result["publishingType"].title())
        if result["startDate"]:
            details.append(result["startDate"][:4])
        if result["totalChapters"]:
            details.append(_("{} chapters").format(result["totalChapters"]))

        row = Adw.ActionRow(
            title=GLib.markup_escape_text(result["title"]),
            subtitle=GLib.markup_escape_text(" · ".join(details)),
        )
        row.add_prefix(self.make_logo(result["coverUrl"], 40, 60))
        button = Gtk.Button(label=_("Track"), valign=Gtk.Align.CENTER)
        button.connect("clicked", self.on_result_chosen, tracker, result)
        row.add_suffix(button)
        row.set_activatable_widget(button)
        self.results_group.add(row)
        self.result_rows.append(row)

    def on_result_chosen(self, button, tracker, result):
        button.set_sensitive(False)
        asyncio.create_task(self.bind(tracker, result))

    async def bind(self, tracker, result):
        try:
            await self.suwayomi.bindTrack(self.manga.id, tracker["id"], result["remoteId"])
        except Exception as error:
            print("Starting tracking failed:", error)
            self.show_toast(_("Couldn't start tracking"))
            return
        self.navigation.pop()
        await self.load()
