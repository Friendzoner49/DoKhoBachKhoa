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


def backup_now(prune: bool = True) -> Path | None:
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

    if prune:
        _prune()
    return dest


def _prune(keep: int = KEEP) -> None:
    backups = sorted(backups_dir().glob("shop-*.sqlite"))
    for old in backups[:-keep]:
        old.unlink(missing_ok=True)


def list_backups() -> list[Path]:
    """Newest first, so a restore dialog can show the most useful one on top."""
    return sorted(backups_dir().glob("shop-*.sqlite"), reverse=True)


class RestoreError(Exception):
    pass


def restore_backup(src: Path) -> None:
    """Overwrite the real ledger with an older snapshot. Caller must close
    every open connection to db_path() first -- sqlite3.connect() here
    would otherwise create or open the destination with a stale lock.
    A fresh safety-net backup_now(prune=False) is the caller's job, not
    this function's, so it stays easy to test without touching real
    backups. Opens src read-only so a missing/renamed file raises instead
    of sqlite3 silently creating an empty database in its place -- that
    empty database would otherwise get copied straight over the real
    ledger."""
    try:
        src_conn = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
        src_conn.execute("SELECT 1 FROM products LIMIT 1")
    except sqlite3.Error as exc:
        raise RestoreError(f"Bản sao lưu không đọc được hoặc không hợp lệ: {src}") from exc

    dest = db_path()
    dest_conn = sqlite3.connect(dest)
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()
