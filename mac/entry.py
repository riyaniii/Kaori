"""PyInstaller entry point for the macOS build.

Mirrors src/kaori.in's frozen-executable behaviour, but as a committed script
PyInstaller can analyse. It:

  1. points GI_TYPELIB_PATH at the bundled typelibs (so gi can resolve Gtk/Adw),
  2. points PATH/JAVA_HOME at the bundled Azul Zulu JRE (so Suwayomi starts
     without a system Java),
  3. points GSETTINGS_SCHEMA_DIR at the bundled schema,
  4. registers the bundled gresource,
  5. hands off to kaori.main.

Data layout inside the frozen bundle (PyInstaller 6 onedir):

  Contents/Resources/Kaori            <- the executable
  Contents/Resources/_internal/       <- sys._MEIPASS
    share/kaori/kaori.gresource
    share/kaori/version
    share/glib-2.0/schemas/
    share/locale/<lang>/LC_MESSAGES/kaori.mo
    girepository-1.0/*.typelib
    runtime/bin/java                  <- not named "jre": a directory called
                                         jre next to the jar breaks Suwayomi's
                                         GraphQL class scanning
    Suwayomi-Server.jar               <- matches main.py's JAR path derivation
"""

import gettext
import locale
import os
import signal
import sys


def frozen_base() -> str:
    # In a PyInstaller onedir build this is the _internal/ dir next to the exe.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _prepend_env(name: str, value: str) -> None:
    existing = os.environ.get(name, "")
    os.environ[name] = value + (os.pathsep + existing if existing else "")


# PyInstaller's `gi` runtime hook points GI_TYPELIB_PATH at its bundled
# gi_typelibs/. Also add a girepository-1.0/ dir if one was copied in by hand
# (defensive fallback -- without resolvable typelibs the app dies at the
# `gi.require_version` calls below with "Namespace Gtk not available").
_typelib_dir = os.path.join(frozen_base(), "girepository-1.0")
if os.path.isdir(_typelib_dir):
    _prepend_env("GI_TYPELIB_PATH", _typelib_dir)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio

APPLICATION_ID = "io.github.riyaniii.Kaori"


def read_version(pkgdatadir: str) -> str:
    try:
        with open(os.path.join(pkgdatadir, "version"), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def main() -> int:
    base = frozen_base()
    pkgdatadir = os.path.join(base, "share", "kaori")
    localedir = os.path.join(base, "share", "locale")
    schemadir = os.path.join(base, "share", "glib-2.0", "schemas")
    jre_bin = os.path.join(base, "runtime", "bin")

    # Prefer the bundled JRE so the Suwayomi server can be started out of the box.
    if os.path.isdir(jre_bin):
        os.environ["JAVA_HOME"] = os.path.dirname(jre_bin)
        _prepend_env("PATH", jre_bin)

    if os.path.isdir(schemadir):
        os.environ["GSETTINGS_SCHEMA_DIR"] = schemadir

    sys.path.insert(1, pkgdatadir)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # locale.bindtextdomain() needs libintl and is missing from some macOS Python
    # builds; gettext's binding below still localises our own strings, so this is
    # informational only (not the cause of any startup failure).
    if hasattr(locale, "bindtextdomain"):
        locale.bindtextdomain("kaori", localedir)
        locale.textdomain("kaori")

    try:
        gettext.bindtextdomain("kaori", localedir)
        gettext.textdomain("kaori")
    except AttributeError:
        print("Translations unavailable.", file=sys.stderr)

    resource = Gio.Resource.load(os.path.join(pkgdatadir, "kaori.gresource"))
    resource._register()

    from kaori import main as kaori_main

    return kaori_main.main(read_version(pkgdatadir))


if __name__ == "__main__":
    sys.exit(main())
