import asyncio
from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk

STRATEGIES = ("PROMPT", "KEEP_LOCAL", "KEEP_REMOTE", "DISABLED")
STRATEGY_SETTINGS = {
    "kosync_forward_row": "koreaderSyncStrategyForward",
    "kosync_backward_row": "koreaderSyncStrategyBackward",
}


def form_dialog(title, rows, button_label, on_submit, intro=None):
    list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
    for row in rows:
        list_box.append(row)

    button = Gtk.Button(label=button_label, halign=Gtk.Align.CENTER, css_classes=["suggested-action", "pill"])

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                  margin_start=12, margin_end=12, margin_bottom=12)
    if intro:
        box.append(intro)
    box.append(list_box)
    box.append(button)

    toolbar_view = Adw.ToolbarView(content=Adw.Clamp(maximum_size=360, child=box))
    toolbar_view.add_top_bar(Adw.HeaderBar())
    dialog = Adw.Dialog(title=title, content_width=380, child=toolbar_view)

    def submit(*args):
        dialog.close()
        on_submit()

    button.connect("clicked", submit)
    for row in rows:
        row.connect("entry-activated", submit)
    return dialog


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/preferences/tracking.ui')
class KaoriTrackingPreferences(Adw.PreferencesPage):
    __gtype_name__ = "KaoriTrackingPreferences"

    trackers_group = Gtk.Template.Child()
    kosync_row = Gtk.Template.Child()
    kosync_button = Gtk.Template.Child()
    kosync_forward_row = Gtk.Template.Child()
    kosync_backward_row = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.tracker_rows = []
        self.kosync_signed_in = False
        self.loaded = False
        asyncio.create_task(self.load())

    def show_toast(self, message):
        dialog = self.get_ancestor(Adw.PreferencesDialog)
        if dialog:
            dialog.add_toast(Adw.Toast(title=message))

    def present_dialog(self, dialog):
        dialog.present(self.get_ancestor(Adw.PreferencesDialog))

    async def load(self):
        try:
            settings = await self.suwayomi.getServerSettings()
            await asyncio.gather(self.load_trackers(), self.load_kosync())
        except Exception as error:
            print("Loading tracking settings failed:", error)
            return
        for name, key in STRATEGY_SETTINGS.items():
            if settings[key] in STRATEGIES:
                getattr(self, name).set_selected(STRATEGIES.index(settings[key]))
        self.loaded = True

    async def load_trackers(self):
        trackers = await self.suwayomi.getTrackers()
        for row in self.tracker_rows:
            self.trackers_group.remove(row)
        self.tracker_rows = []
        for tracker in trackers:
            self.add_tracker_row(tracker)

    def add_tracker_row(self, tracker):
        row = Adw.ActionRow(title=tracker["name"])
        icon = Gtk.Image(pixel_size=32, css_classes=["icon-dropshadow"])
        row.add_prefix(icon)
        asyncio.create_task(self.load_icon(icon, tracker))

        if tracker["isLoggedIn"]:
            row.set_subtitle(_("Signed in"))
            button = Gtk.Button(label=_("Sign Out"), valign=Gtk.Align.CENTER)
            button.connect("clicked", self.on_sign_out_clicked, tracker)
        else:
            row.set_subtitle(_("Not signed in"))
            button = Gtk.Button(label=_("Sign In"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
            button.connect("clicked", self.on_sign_in_clicked, tracker)
        row.add_suffix(button)

        self.trackers_group.add(row)
        self.tracker_rows.append(row)

    async def load_icon(self, image, tracker):
        try:
            image.set_from_paintable(await self.suwayomi.getPaintable(self.suwayomi.trackerIconUrl(tracker)))
        except Exception as error:
            print("Tracker icon failed:", error)

    def on_sign_out_clicked(self, button, tracker):
        asyncio.create_task(self.sign_out(tracker))

    async def sign_out(self, tracker):
        try:
            await self.suwayomi.logoutTracker(tracker["id"])
            await self.load_trackers()
        except Exception as error:
            print("Signing out failed:", error)
            self.show_toast(_("Couldn't sign out"))

    def on_sign_in_clicked(self, button, tracker):
        if tracker["authUrl"]:
            self.show_oauth_dialog(tracker)
        else:
            self.show_credentials_dialog(tracker)

    def show_oauth_dialog(self, tracker):
        address_row = Adw.EntryRow(title=_("Address After Signing In"), input_purpose=Gtk.InputPurpose.URL)

        open_button = Gtk.Button(label=_("Open Sign-In Page"), halign=Gtk.Align.CENTER, css_classes=["pill"])
        open_button.connect("clicked", lambda *args: Gtk.UriLauncher(uri=tracker["authUrl"]).launch(self.get_root(), None, None))

        steps = Gtk.Label(
            label=_("Sign in on the page that opens. When you're sent to a new page, copy its address from the browser and paste it below."),
            wrap=True,
            xalign=0,
        )
        intro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        intro.append(steps)
        intro.append(open_button)

        def submit():
            asyncio.create_task(self.sign_in_oauth(tracker, address_row.get_text().strip()))

        title = _("Sign In to {}").format(tracker["name"])
        self.present_dialog(form_dialog(title, [address_row], _("Sign In"), submit, intro))

    async def sign_in_oauth(self, tracker, address):
        if not address:
            return
        try:
            signed_in = await self.suwayomi.loginTrackerOAuth(tracker["id"], address)
        except Exception as error:
            print("Tracker sign-in failed:", error)
            signed_in = False
        await self.finish_sign_in(tracker, signed_in)

    def show_credentials_dialog(self, tracker):
        username_row = Adw.EntryRow(title=_("Username"))
        password_row = Adw.PasswordEntryRow(title=_("Password"))

        def submit():
            asyncio.create_task(self.sign_in_credentials(
                tracker, username_row.get_text().strip(), password_row.get_text()))

        title = _("Sign In to {}").format(tracker["name"])
        self.present_dialog(form_dialog(title, [username_row, password_row], _("Sign In"), submit))

    async def sign_in_credentials(self, tracker, username, password):
        try:
            signed_in = await self.suwayomi.loginTrackerCredentials(tracker["id"], username, password)
        except Exception as error:
            print("Tracker sign-in failed:", error)
            signed_in = False
        await self.finish_sign_in(tracker, signed_in)

    async def finish_sign_in(self, tracker, signed_in):
        if signed_in:
            self.show_toast(_("Signed in to {}").format(tracker["name"]))
        else:
            self.show_toast(_("Couldn't sign in to {}").format(tracker["name"]))
        await self.load_trackers()

    async def load_kosync(self):
        status = await self.suwayomi.getKoSyncStatus()
        self.show_kosync_status(status)

    def show_kosync_status(self, status):
        self.kosync_signed_in = status["isLoggedIn"]
        if self.kosync_signed_in:
            self.kosync_row.set_subtitle(_("{} on {}").format(status["username"], status["serverAddress"]))
            self.kosync_button.set_label(_("Sign Out"))
            self.kosync_button.remove_css_class("suggested-action")
        else:
            self.kosync_row.set_subtitle(_("Not signed in"))
            self.kosync_button.set_label(_("Sign In"))
            self.kosync_button.add_css_class("suggested-action")

    @Gtk.Template.Callback()
    def on_kosync_clicked(self, button):
        if self.kosync_signed_in:
            asyncio.create_task(self.kosync_sign_out())
            return

        server_row = Adw.EntryRow(title=_("Server Address"), input_purpose=Gtk.InputPurpose.URL,
                                  text="https://sync.koreader.rocks")
        username_row = Adw.EntryRow(title=_("Username"))
        password_row = Adw.PasswordEntryRow(title=_("Password"))

        def submit():
            asyncio.create_task(self.kosync_sign_in(
                server_row.get_text().strip(), username_row.get_text().strip(), password_row.get_text()))

        rows = [server_row, username_row, password_row]
        self.present_dialog(form_dialog(_("KOReader Sync"), rows, _("Sign In"), submit))

    async def kosync_sign_in(self, server, username, password):
        try:
            answer = await self.suwayomi.connectKoSync(server, username, password)
        except Exception as error:
            print("KOReader sign-in failed:", error)
            self.show_toast(_("Couldn't sign in to KOReader Sync"))
            return
        self.show_kosync_status(answer["status"])
        if not answer["status"]["isLoggedIn"]:
            self.show_toast(answer["message"] or _("Couldn't sign in to KOReader Sync"))

    async def kosync_sign_out(self):
        try:
            await self.suwayomi.logoutKoSync()
            await self.load_kosync()
        except Exception as error:
            print("KOReader sign-out failed:", error)
            self.show_toast(_("Couldn't sign out"))

    @Gtk.Template.Callback()
    def on_strategy_changed(self, row, pspec):
        if not self.loaded:
            return
        key = STRATEGY_SETTINGS[Gtk.Buildable.get_buildable_id(row)]
        asyncio.create_task(self.suwayomi.setServerSettings(**{key: STRATEGIES[row.get_selected()]}))
