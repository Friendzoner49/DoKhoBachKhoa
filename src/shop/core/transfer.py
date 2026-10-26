"""Move all data (the database + supplier-invoice photos) to another
machine in one file -- requested so the owner can keep working
seamlessly between this Windows machine and the Mac build (see
CLAUDE.md mục 7). Model: only one machine is the "live" one at a time.
Importing a package REPLACES local data after a safety backup; there is
no merge.

Qt-free like every other shop.core module: callers (shop.ui.settings_page)
resolve shop.paths values and pass them in explicitly, so this stays
testable without touching the real data directory.
"""
import json
import platform
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from shop.db.migrate import connect

EXTENSION = ".shopdata"
FORMAT = 1
DB_MEMBER = "shop.sqlite"
PHOTOS_PREFIX = "supplier_invoices/"


class TransferError(Exception):
    """A Vietnamese message safe to show directly in a QMessageBox."""


@dataclass
class Manifest:
    exported_at: str
    schema_version: int
    products: int
    customers: int
    invoices: int
    source_machine: str = ""
    # Carried along so a NEW machine can sync online orders right after
    # importing, without the owner having to dig up the Worker URL/Mã
    # đồng bộ again (shop.ui.settings_page only applies these if the
    # target machine's own settings are still empty -- never overwrites
    # a machine that's already configured).
    bot_sync_url: str = ""
    bot_sync_secret: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Manifest":
        kwargs = {k: d.get(k) for k in cls.__dataclass_fields__}
        # A package without these (an older export, or a foreign file)
        # should read back as "" like a fresh Manifest(...), not None --
        # schema_version missing staying None is deliberate: that's what
        # read_manifest's own explicit check right after this is for.
        for optional in ("source_machine", "bot_sync_url", "bot_sync_secret"):
            kwargs[optional] = kwargs[optional] or ""
        return cls(**kwargs)


def default_export_name() -> str:
    return f"BachHoa705_{datetime.now():%Y-%m-%d_%H%M}{EXTENSION}"


def export_package(
    conn: sqlite3.Connection,
    dest_path: Path,
    photos_dir: Path,
    bot_sync_url: str = "",
    bot_sync_secret: str = "",
) -> Path:
    """Writes a .shopdata zip to the EXACT path given (caller picks the
    name, e.g. via a file-save dialog -- same convention as the app's
    other "Xuất ... ra Excel" buttons) and returns it back."""
    manifest = Manifest(
        exported_at=datetime.now().isoformat(timespec="seconds"),
        schema_version=conn.execute("PRAGMA user_version").fetchone()[0],
        products=conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        customers=conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        invoices=conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0],
        source_machine=platform.node(),
        bot_sync_url=bot_sync_url,
        bot_sync_secret=bot_sync_secret,
    )
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        snap_path = Path(tmp) / DB_MEMBER
        snap_conn = sqlite3.connect(snap_path)
        try:
            # sqlite3's backup API takes a consistent snapshot even while
            # conn is a live, in-use connection (same technique as
            # shop.db.backup.backup_now) -- a plain file copy wouldn't be
            # safe to do this directly on conn's own file, and conn may
            # not even BE a file (:memory:, in tests).
            conn.backup(snap_conn)
        finally:
            snap_conn.close()
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps({**asdict(manifest), "format": FORMAT}, ensure_ascii=False))
            z.write(snap_path, DB_MEMBER)
            if photos_dir.exists():
                for f in sorted(photos_dir.iterdir()):
                    if f.is_file():
                        z.write(f, PHOTOS_PREFIX + f.name)
    return dest_path


def read_manifest(path: Path, current_schema_version: int) -> Manifest:
    try:
        with zipfile.ZipFile(path) as z:
            data = json.loads(z.read("manifest.json").decode("utf-8"))
            if DB_MEMBER not in z.namelist():
                raise TransferError("Gói dữ liệu thiếu database, có thể file đã hỏng.")
    except FileNotFoundError as exc:
        raise TransferError(f"Không tìm thấy file: {path}") from exc
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise TransferError(f"File gói dữ liệu bị hỏng hoặc không đúng định dạng: {exc}") from exc
    manifest = Manifest.from_dict(data)
    if manifest.schema_version is None:
        raise TransferError("Không đọc được phiên bản dữ liệu trong gói này.")
    if manifest.schema_version > current_schema_version:
        raise TransferError(
            "Gói dữ liệu này được tạo bởi 1 bản app MỚI HƠN bản đang cài trên máy này. "
            "Hãy cập nhật app trước khi nhập."
        )
    return manifest


def import_package(path: Path, current_schema_version: int, db_path: Path, photos_dir: Path) -> Manifest:
    """Validates the package fully BEFORE touching anything real, then
    replaces db_path AND every supplier-invoice photo the package has
    (overwriting any local file of the same name). This is NOT a merge
    -- the whole database is replaced, so a local "1-hoadon.jpg" left
    over from a DIFFERENT invoice #1 (made on this machine before this
    import) must not keep showing for the package's own invoice #1.
    Caller must close its own sqlite3.Connection to db_path before
    calling this (Windows can't replace a file another handle has
    open), and reopen a fresh one after."""
    manifest = read_manifest(path, current_schema_version)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(path) as z:
            z.extract(DB_MEMBER, tmp)
            photo_names = [n for n in z.namelist() if n.startswith(PHOTOS_PREFIX) and not n.endswith("/")]
            # A package from an older app version is upgraded to the
            # CURRENT schema right here, on the extracted copy -- if
            # migrate() fails, nothing on this machine has been touched.
            upgraded = connect(Path(tmp) / DB_MEMBER)
            upgraded.close()
            if photo_names:
                photos_dir.mkdir(parents=True, exist_ok=True)
                for name in photo_names:
                    target = photos_dir / Path(name).name
                    with z.open(name) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        new_db = db_path.with_suffix(".incoming")
        shutil.copy2(Path(tmp) / DB_MEMBER, new_db)
        new_db.replace(db_path)
    return manifest
