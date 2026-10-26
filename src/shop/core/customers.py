"""Customers: contact info, per-customer markup %, and opening balance
(debt they already owed before this app existed).
"""
import sqlite3
from datetime import datetime, timezone

from shop.core.pricing import PUBLIC_MARKUP_PCT


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_customers(conn: sqlite3.Connection, active_only: bool = True) -> list[dict]:
    sql = "SELECT id, name, address, contact, default_markup_pct, opening_balance, note, active FROM customers"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY name COLLATE VNAME"
    cols = ["id", "name", "address", "contact", "default_markup_pct", "opening_balance", "note", "active"]
    return [dict(zip(cols, row)) for row in conn.execute(sql)]


def get_customer(conn: sqlite3.Connection, customer_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, name, address, contact, default_markup_pct, opening_balance, note, active FROM customers WHERE id = ?",
        (customer_id,),
    ).fetchone()
    if row is None:
        return None
    cols = ["id", "name", "address", "contact", "default_markup_pct", "opening_balance", "note", "active"]
    return dict(zip(cols, row))


def add_customer(
    conn: sqlite3.Connection,
    name: str,
    address: str | None = None,
    contact: str | None = None,
    default_markup_pct: float = float(PUBLIC_MARKUP_PCT),
    opening_balance: int = 0,
    note: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO customers (name, address, contact, default_markup_pct, opening_balance, note, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (name, address, contact, default_markup_pct, opening_balance, note, _now()),
    )
    conn.commit()
    return cur.lastrowid


def update_customer(conn: sqlite3.Connection, customer_id: int, **fields) -> None:
    if not fields:
        return
    allowed = {"name", "address", "contact", "default_markup_pct", "opening_balance", "note", "active"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Unknown customer field(s): {unknown}")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE customers SET {set_clause} WHERE id = ?", (*fields.values(), customer_id))
    conn.commit()
