
import glob
import os
import shutil

from PyInstaller.utils.hooks.gi import get_gi_typelibs

ROOT = os.environ["KAORI_ROOT"]
PKGPATH = os.path.join(ROOT, "build", "pypkg")

gresource = os.environ.get("KAORI_GRESOURCE") or os.path.join(
    ROOT, "build", "src", "kaori.gresource"
)

jar_source = glob.glob(os.path.join(ROOT, "src", "Suwayomi-Server*.jar"))[0]
jar = os.path.join(ROOT, "build", "Suwayomi-Server.jar")
shutil.copyfile(jar_source, jar)

binaries, gi_datas, hiddenimports = [], [], []
for ns, ver in [
    ("GLib", "2.0"), ("GObject", "2.0"), ("Gio", "2.0"), ("GModule", "2.0"),
    ("cairo", "1.0"), ("HarfBuzz", "0.0"), ("Graphene", "1.0"),
    ("Pango", "1.0"), ("PangoCairo", "1.0"), ("GdkPixbuf", "2.0"),
    ("Gdk", "4.0"), ("Gsk", "4.0"), ("Gtk", "4.0"), ("Adw", "1"),
]:
    try:
        b, d, h = get_gi_typelibs(ns, ver)
        binaries += b
        gi_datas += d
        hiddenimports += h
    except Exception as exc:
        print(f"WARN: could not collect GI namespace {ns}-{ver}: {exc}")

hiddenimports += ["gi", "cairo", "gi._gi_cairo"]

a = Analysis(
    [os.path.join(ROOT, "mac", "entry.py")],
    pathex=[PKGPATH],
    binaries=binaries,
    datas=gi_datas + [
        (gresource, "share/kaori"),
        (os.path.join(ROOT, "build", "version"), "share/kaori"),
        (os.path.join(ROOT, "build", "schemas"), "share/glib-2.0/schemas"),
        (os.path.join(ROOT, "build", "locale"), "share/locale"),
        (jar, "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={
        "gi": {
            "icons": ["Adwaita"],
            "themes": ["Adwaita"],
            "module-versions": {
                "Gtk": "4.0",
                "Adw": "1",
            },
        }
    },
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kaori",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Kaori",
)
