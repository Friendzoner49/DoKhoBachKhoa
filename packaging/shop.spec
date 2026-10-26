# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec, shared shape for Windows and macOS (DiBeKho's
pattern: --onedir only, no --onefile -- that mode unpacks to a temp
dir on every launch and can leave junk behind on a hard crash).

Build with: uv run pyinstaller packaging/shop.spec --distpath packaging/dist --workpath packaging/build
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent  # SPECPATH is .../packaging; project root is one level up

# Display/bundle name only -- the exe, dist folder and .app name. Deliberately
# NOT the same constant as shop.paths.APP_NAME ("ShopApp"), which drives
# config.json's location, the default Documents data folder and the backups
# folder -- renaming THAT would make the app open empty books instead of the
# real ledger at K:\705bot\data. See CLAUDE.md mục 2/7 on why these two names
# are allowed to differ.
DIST_NAME = "BachHoa705"
ICON_ICO = ROOT / "src" / "shop" / "ui" / "icon.ico"
ICON_ICNS = ROOT / "packaging" / "brand" / "icon.icns"

# Bundles src/shop/db/migrations/*.sql and src/shop/site_template/index.html
# -- neither is auto-discovered by PyInstaller's import analysis since
# they're read via importlib.resources, not imported as Python code.
datas = collect_data_files("shop")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Not installed (pyside6-essentials only) and not used by this
        # widget-only app; listed explicitly so a future dependency
        # change doesn't silently drag heavy Qt modules back in.
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
    ],
    noarchive=False,
)

# Software OpenGL rasterizer fallback -- a plain QtWidgets app never
# needs it, and it's ~15-20MB (DiBeKho excluded the same binary).
a.binaries = [b for b in a.binaries if "opengl32sw" not in b[0].lower()]

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=DIST_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON_ICO),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=DIST_NAME,
)

# macOS: wrap the onedir build into a double-clickable .app bundle too.
import sys

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{DIST_NAME}.app",
        icon=str(ICON_ICNS),
        # Deliberately UNCHANGED even though DIST_NAME changed: macOS treats
        # the bundle identifier as the app's durable identity. Changing it
        # makes the OS ask for the Documents folder permission again (same
        # folder, same data, just re-prompted) -- see CLAUDE.md mục 7.
        bundle_identifier="vn.shopapp.app",
        info_plist={
            "CFBundleDisplayName": DIST_NAME,
            "NSHighResolutionCapable": True,
            # pyside6-essentials' own wheel for this Python/arch only ships
            # for macosx_14_0+ (confirmed via uv.lock) -- a lower floor
            # here would let the app launch on an OS its own Qt build
            # doesn't actually support.
            "LSMinimumSystemVersion": "14.0",
            # shop.paths._default_data_dir() uses ~/Documents/ShopApp once
            # frozen (APP_NAME there is unchanged -- see the comment by
            # DIST_NAME above) -- without this, macOS silently denies that
            # folder access instead of prompting (DiBeKho hit the same thing).
            "NSDocumentsFolderUsageDescription": "BachHoa705 lưu dữ liệu bán hàng trong thư mục Documents.",
        },
    )
