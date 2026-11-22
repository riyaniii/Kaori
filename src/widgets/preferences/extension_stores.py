import asyncio
from gi.repository import Adw, Gio, Gtk


@Gtk.Template(resource_path='/io/github/riyaniii/Kaori/preferences/extension_stores.ui')
class ExtensionStoresDialog(Adw.Dialog):
    __gtype_name__ = "KaoriExtensionStoresDialog"

    url_entry = Gtk.Template.Child()
    stores_group = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.suwayomi = Gio.Application.get_default().suwayomi
        self.rows = {}

        asyncio.create_task(self.load())

    async def load(self):
        try:
            stores = await self.suwayomi.getExtensionStores()
        except Exception as error:
            print("Loading extension stores failed:", error)
            return

        for store in stores:
            self.add_row(store['indexUrl'])

    def add_row(self, url):
        if url in self.rows:
            return

        row = Adw.ActionRow(title=url, title_selectable=True)
        button = Gtk.Button(
            icon_name="user-trash-symbolic",
            valign=Gtk.Align.CENTER,
            css_classes=["flat"],
        )
        button.connect("clicked", self.on_remove_clicked, url)
        row.add_suffix(button)

        self.stores_group.add(row)
        self.rows[url] = row

    @Gtk.Template.Callback()
    def on_add(self, entry):
        url = entry.get_text().strip()
        if not url.startswith(("http://", "https://")):
            entry.add_css_class("error")
            return

        entry.remove_css_class("error")
        entry.set_sensitive(False)
        asyncio.create_task(self.add_store(entry, url))

    async def add_store(self, entry, url):
        try:
            store = await self.suwayomi.addExtensionStore(url)
        except Exception as error:
            entry.add_css_class("error")
            print("Adding extension store failed:", error)
        else:
            entry.set_text("")
            self.add_row(store['indexUrl'])
        finally:
            entry.set_sensitive(True)

    def on_remove_clicked(self, button, url):
        button.set_sensitive(False)
        asyncio.create_task(self.remove_store(button, url))

    async def remove_store(self, button, url):
        try:
            await self.suwayomi.removeExtensionStore(url)
        except Exception as error:
            button.set_sensitive(True)
            print("Removing extension store failed:", error)
        else:
            self.stores_group.remove(self.rows.pop(url))
