"""Shared SQLite connection + migration runner.

Every entry point (catalog tools, invoice app, later the bot) calls
connect() and gets the one database at shop.paths.db_path(). Migrations
are loaded via importlib.resources so they're found the same way whether
running from source or from a PyInstaller bundle.
"""
import sqlite3
from importlib import resources
from pathlib import Path

from shop.core.text import strip_accents
from shop.paths import db_path


def _vn_collate(a: str, b: str) -> int:
    """Approximate Vietnamese alphabetical order (accent-insensitive
    primary key, so 'Đậu' sorts with the D's instead of after 'Z'),
    falling back to the accented string to break ties."""
    ka, kb = (strip_accents(a).lower(), a), (strip_accents(b).lower(), b)
    return -1 if ka < kb else (1 if ka > kb else 0)


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or db_path())
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_collation("VNAME", _vn_collate)
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    migrations_dir = resources.files("shop.db") / "migrations"
    files = sorted(
        (f for f in migrations_dir.iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    for f in files:
        version = int(f.name.split("_", 1)[0])
        if version <= current:
            continue
        sql = f.read_text(encoding="utf-8")
        # Wrapped so a failure partway through a migration never leaves
        # the schema half-applied with user_version still showing "done".
        conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")


if __name__ == "__main__":
    conn = connect()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    print(f"Database ready at {db_path()} (schema version {version})")
