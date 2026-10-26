"""Automatic backups of the ledger database. This is the only copy of
the shop's debt/profit records, so a snapshot is taken on every app
start, before anything can possibly go wrong that session.
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from shop.paths import backups_dir, db_path

KEEP = 14


def backup_now() -> Path | None:
    if os.environ.get("SHOP_DATA_DIR"):
        # Self-test / build-verification mode: all real backups share one
        # shop-*.sqlite + keep-14 pool, so backing up a scratch DB here
        # would prune away real backups of the actual ledger.
        return None

    src = db_path()
    if not src.exists():
        return None

    dest = backups_dir() / f"shop-{datetime.now():%Y%m%d-%H%M%S}.sqlite"
    src_conn = sqlite3.connect(src)
    dest_conn = sqlite3.connect(dest)
    try:
        # sqlite3's backup API takes a consistent snapshot even while src
        # is open elsewhere, unlike a plain file copy.
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()

    _prune()
    return dest


def _prune(keep: int = KEEP) -> None:
    backups = sorted(backups_dir().glob("shop-*.sqlite"))
    for old in backups[:-keep]:
        old.unlink(missing_ok=True)
