from collections.abc import Callable
from dataclasses import dataclass, field

from gi.repository import Gio, GLib

ITEM_PATH = '/StatusNotifierItem'
MENU_PATH = '/MenuBar'
MENU_INTERFACE = 'com.canonical.dbusmenu'

ITEM_XML = '''
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="Activate">
      <arg type="i" direction="in"/>
      <arg type="i" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" direction="in"/>
      <arg type="i" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg type="i" direction="in"/>
      <arg type="i" direction="in"/>
    </method>
    <method name="Scroll">
      <arg type="i" direction="in"/>
      <arg type="s" direction="in"/>
    </method>
  </interface>
</node>
'''

MENU_XML = '''
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <method name="GetLayout">
      <arg type="i" direction="in"/>
      <arg type="i" direction="in"/>
      <arg type="as" direction="in"/>
      <arg type="u" direction="out"/>
      <arg type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" direction="in"/>
      <arg type="as" direction="in"/>
      <arg type="a(ia{sv})" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" direction="in"/>
      <arg type="s" direction="in"/>
      <arg type="v" direction="in"/>
      <arg type="u" direction="in"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" direction="in"/>
      <arg type="b" direction="out"/>
    </method>
    <signal name="LayoutUpdated">
      <arg type="u"/>
      <arg type="i"/>
    </signal>
  </interface>
</node>
'''


@dataclass
class Entry:
    label: str = ''
    callback: Callable | None = None
    enabled: bool = True
    separator: bool = False
    children: list = field(default_factory=list)


class Tray:

    def __init__(self, icon: str, title: str, entries: list) -> None:
        self.icon = icon
        self.title = title
        self.revision = 1
        self.set_entries_data(entries)
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        item_info = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self.item_id = self.connection.register_object(
            ITEM_PATH, item_info, self.on_item_call, self.on_item_property, None)
        self.menu_id = self.connection.register_object(
            MENU_PATH, menu_info, self.on_menu_call, self.on_menu_property, None)

        self.connection.call(
            'org.kde.StatusNotifierWatcher',
            '/StatusNotifierWatcher',
            'org.kde.StatusNotifierWatcher',
            'RegisterStatusNotifierItem',
            GLib.Variant('(s)', (ITEM_PATH,)),
            None, Gio.DBusCallFlags.NONE, -1, None, self.on_registered)

    def close(self) -> None:
        self.connection.unregister_object(self.item_id)
        self.connection.unregister_object(self.menu_id)

    def set_entries_data(self, entries: list) -> None:
        self.entries = entries
        self.items = {}
        self.children = {0: []}
        self.add_entries(entries, 0)

    def add_entries(self, entries: list, parent: int) -> None:
        for entry in entries:
            item_id = len(self.items) + 1
            self.items[item_id] = entry
            self.children[parent].append(item_id)
            self.children[item_id] = []
            self.add_entries(entry.children, item_id)

    def set_entries(self, entries: list) -> None:
        if entries == self.entries:
            return
        self.set_entries_data(entries)
        self.revision += 1
        self.connection.emit_signal(
            None, MENU_PATH, MENU_INTERFACE, 'LayoutUpdated',
            GLib.Variant('(ui)', (self.revision, 0)))

    def on_registered(self, connection, result) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error as e:
            print("Tray unavailable:", e.message)

    def on_item_property(self, connection, sender, path, interface, name):
        values = {
            'Category': GLib.Variant('s', 'ApplicationStatus'),
            'Id': GLib.Variant('s', self.icon),
            'Title': GLib.Variant('s', self.title),
            'Status': GLib.Variant('s', 'Active'),
            'IconName': GLib.Variant('s', self.icon),
            'ItemIsMenu': GLib.Variant('b', False),
            'Menu': GLib.Variant('o', MENU_PATH),
        }
        return values.get(name)

    def on_item_call(self, connection, sender, path, interface, method, parameters, invocation) -> None:
        if method == 'Activate' and self.entries[0].callback:
            self.entries[0].callback()
        invocation.return_value(None)

    def on_menu_property(self, connection, sender, path, interface, name):
        values = {
            'Version': GLib.Variant('u', 3),
            'TextDirection': GLib.Variant('s', 'ltr'),
            'Status': GLib.Variant('s', 'normal'),
        }
        return values.get(name)

    def entry_properties(self, item_id: int) -> dict:
        if item_id == 0:
            return {'children-display': GLib.Variant('s', 'submenu')}
        entry = self.items[item_id]
        if entry.separator:
            return {'type': GLib.Variant('s', 'separator')}
        properties = {
            'label': GLib.Variant('s', entry.label),
            'enabled': GLib.Variant('b', entry.enabled),
        }
        if entry.children:
            properties['children-display'] = GLib.Variant('s', 'submenu')
        return properties

    def layout(self, item_id: int, depth: int) -> tuple:
        children = []
        if depth != 0:
            children = [
                GLib.Variant('(ia{sv}av)', self.layout(child, depth - 1 if depth > 0 else depth))
                for child in self.children[item_id]
            ]
        return (item_id, self.entry_properties(item_id), children)

    def on_menu_call(self, connection, sender, path, interface, method, parameters, invocation) -> None:
        if method == 'GetLayout':
            parent, depth, names = parameters.unpack()
            if parent not in self.children:
                parent = 0
            invocation.return_value(GLib.Variant(
                '(u(ia{sv}av))', (self.revision, self.layout(parent, depth))))
        elif method == 'GetGroupProperties':
            ids = parameters.unpack()[0]
            items = [
                (item_id, self.entry_properties(item_id))
                for item_id in self.items
                if not ids or item_id in ids
            ]
            invocation.return_value(GLib.Variant('(a(ia{sv}))', (items,)))
        elif method == 'Event':
            item_id, event, data, timestamp = parameters.unpack()
            entry = self.items.get(item_id)
            if event == 'clicked' and entry and entry.enabled and entry.callback:
                entry.callback()
            invocation.return_value(None)
        elif method == 'AboutToShow':
            invocation.return_value(GLib.Variant('(b)', (False,)))
