import asyncio
import os

from gi.repository import Gtk, Adw, Gio, GLib

from ..constants import DONATE_URL, GUIDE_URL

LOCAL_SOURCE_URL = "https://github.com/Suwayomi/Suwayomi-Server/wiki/Local-Source"


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/setup.ui')
class SetupWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'KaoriSetupWindow'

    toolbar = Gtk.Template.Child()
    carousel = Gtk.Template.Child()
    status_page = Gtk.Template.Child()
    local_row = Gtk.Template.Child()
    remote_row = Gtk.Template.Child()
    repo_page = Gtk.Template.Child()
    extensions_page = Gtk.Template.Child()
    local_page = Gtk.Template.Child()
    folder_row = Gtk.Template.Child()
    done_page = Gtk.Template.Child()
    back_button = Gtk.Template.Child()
    next_button = Gtk.Template.Child()

    def __init__(self, error: str | None = None, guided: bool | None = None, **kwargs):
        super().__init__(**kwargs)
        self.app = Gio.Application.get_default()
        if guided is None:
            guided = not self.app.settings.get_boolean('welcome-shown')
        self.guided = guided
        self.mode = "local"
        self.url = ""
        self.local_folder = None
        self.local_path = ""
        self.current = 0

        if error:
            self.status_page.set_description(error)

        self.carousel.remove(self.local_page)
        if guided:
            self.toolbar.set_reveal_bottom_bars(True)
        else:
            for page in (self.repo_page, self.extensions_page, self.done_page):
                self.carousel.remove(page)
        self.update_nav()

    def update_nav(self):
        last = self.carousel.get_n_pages() - 1
        self.back_button.set_visible(self.current > 0)
        self.next_button.set_visible(self.current > 0)
        self.next_button.set_label('Get Started' if self.current >= last else 'Next')

    def go_to(self, index: int):
        self.carousel.scroll_to(self.carousel.get_nth_page(index), True)

    def open_uri(self, url: str):
        Gtk.UriLauncher(uri=url).launch(self, None, None)

    def set_local_step(self, enabled: bool):
        present = self.local_page.get_parent() is not None
        if enabled and not present:
            self.update_folder_row()
            self.carousel.insert(self.local_page, self.carousel.get_n_pages() - 1)
        elif not enabled and present:
            self.carousel.remove(self.local_page)
        self.update_nav()

    def update_folder_row(self):
        self.local_folder = self.local_path or self.app.server.default_folder('local')
        self.folder_row.set_subtitle(self.local_folder)

    def choose(self, mode: str, url: str):
        if not self.guided:
            self.begin_connect(mode, url)
            return
        self.mode = mode
        self.url = url
        self.set_local_step(mode == "local")
        self.go_to(1)

    @Gtk.Template.Callback()
    def on_position_changed(self, carousel, pspec):
        self.current = round(carousel.get_position())
        self.update_nav()

    @Gtk.Template.Callback()
    def on_back(self, button):
        if self.current > 0:
            self.go_to(self.current - 1)

    @Gtk.Template.Callback()
    def on_next(self, button):
        if self.current >= self.carousel.get_n_pages() - 1:
            self.begin_connect(self.mode, self.url)
        else:
            self.go_to(self.current + 1)

    @Gtk.Template.Callback()
    def on_guide(self, button):
        self.open_uri(GUIDE_URL)

    @Gtk.Template.Callback()
    def on_local_guide(self, button):
        self.open_uri(LOCAL_SOURCE_URL)

    @Gtk.Template.Callback()
    def on_donate(self, button):
        self.open_uri(DONATE_URL)

    @Gtk.Template.Callback()
    def on_path_activated(self, row):
        Gtk.FileDialog(title=row.get_title()).select_folder(
            self, None, self.on_path_selected
        )

    def on_path_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        self.local_path = folder.get_path()
        self.update_folder_row()

    @Gtk.Template.Callback()
    def on_path_cleared(self, button):
        self.local_path = ""
        self.update_folder_row()

    @Gtk.Template.Callback()
    def on_open_folder(self, button):
        try:
            os.makedirs(self.local_folder, exist_ok=True)
        except OSError:
            return
        Gtk.FileLauncher(file=Gio.File.new_for_path(self.local_folder)).launch(self, None, None)

    @Gtk.Template.Callback()
    def on_local_activated(self, row):
        self.choose("local", "")

    @Gtk.Template.Callback()
    def on_remote_activated(self, row):
        self.show_remote_dialog()

    def show_remote_dialog(self):
        url_row = Adw.EntryRow(title="Server URL", input_purpose=Gtk.InputPurpose.URL)
        url_row.set_text("http://localhost:4567")

        list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        list_box.add_css_class("boxed-list")
        list_box.append(url_row)

        connect_button = Gtk.Button(label="Continue", sensitive=False, halign=Gtk.Align.CENTER)
        connect_button.add_css_class("suggested-action")
        connect_button.add_css_class("pill")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        content_box.set_margin_bottom(12)
        content_box.append(list_box)
        content_box.append(connect_button)

        clamp = Adw.Clamp(maximum_size=340)
        clamp.set_child(content_box)

        header_bar = Adw.HeaderBar()

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(clamp)

        dialog = Adw.Dialog(title="Remote Server", content_width=360)
        dialog.set_child(toolbar_view)

        def update_sensitivity(*_):
            connect_button.set_sensitive(bool(url_row.get_text().strip()))

        def do_connect(*_):
            url = url_row.get_text().strip().rstrip('/')
            if not url:
                return
            if not url.startswith(('http://', 'https://')):
                url = f"http://{url}"
            dialog.close()
            self.choose("remote", url)

        update_sensitivity()
        url_row.connect("changed", update_sensitivity)
        url_row.connect("entry-activated", do_connect)
        connect_button.connect("clicked", do_connect)

        dialog.present(self)

    def begin_connect(self, mode: str, url: str):
        self.set_visible(False)
        asyncio.create_task(self.try_connect(mode, url))

    async def save_local_path(self):
        try:
            await self.app.suwayomi.setServerSettings(localSourcePath=self.local_path)
        except Exception as e:
            print(f'[kaori] saving local source path failed: {e!r}')

    async def try_connect(self, mode: str, url: str):
        try:
            if await self.app.launch(mode, url):
                if self.guided:
                    self.app.settings.set_boolean('welcome-shown', True)
                    if mode == "local" and self.local_path:
                        await self.save_local_path()
                self.close()
                return
            error = self.app.failure_message(mode)
        except Exception as e:
            print(f'[kaori] launch raised: {e!r}')
            error = f"Failed to start: {e}"
        self.set_visible(True)
        if self.guided:
            self.go_to(0)
        self.status_page.set_description(error)
