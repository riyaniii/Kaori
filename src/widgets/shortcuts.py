from gi.repository import Gtk

def build_shortcuts():
    builder = Gtk.Builder.new_from_resource('/io/github/riyaniii/Kaori/shortcuts.ui')
    return builder.get_object("shortcuts_dialog")
