"""Payments a customer has made against their running balance."""
import sqlite3
from datetime import date, datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add_payment(conn: sqlite3.Connection, customer_id: int, amount: int, paid_at: str | None = None, note: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO payments (customer_id, amount, paid_at, note) VALUES (?, ?, ?, ?)",
        (customer_id, amount, paid_at or date.today().isoformat(), note),
    )
    conn.commit()
    return cur.lastrowid


def list_payments(conn: sqlite3.Connection, customer_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, amount, paid_at, note FROM payments WHERE customer_id = ? ORDER BY paid_at DESC, id DESC",
        (customer_id,),
    ).fetchall()
    cols = ["id", "amount", "paid_at", "note"]
    return [dict(zip(cols, row)) for row in rows]


def delete_payment(conn: sqlite3.Connection, payment_id: int) -> None:
    conn.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    conn.commit()
