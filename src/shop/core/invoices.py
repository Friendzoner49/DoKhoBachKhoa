"""Invoices: draft -> add/edit/remove lines -> finalize. A finalized
invoice's lines keep their cost/price snapshot forever, so editing a
product's current cost later never changes an old invoice's totals.

Only finalized invoices count toward debt and profit (see
customers_summary.py) — a draft is just work in progress.
"""
import sqlite3
from datetime import date, datetime, timezone

from shop.core import products as products_core
from shop.core.pricing import PUBLIC_MARKUP_PCT
from shop.core.pricing import line_total as calc_line_total
from shop.core.pricing import unit_price as calc_unit_price


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_invoice(conn: sqlite3.Connection, customer_id: int, invoice_date: str | None = None, note: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO invoices (customer_id, invoice_date, status, note, created_at) VALUES (?, ?, 'draft', ?, ?)",
        (customer_id, invoice_date or date.today().isoformat(), note, _now()),
    )
    conn.commit()
    return cur.lastrowid


def add_line(
    conn: sqlite3.Connection,
    invoice_id: int,
    product_code: str,
    qty: float,
    unit_price_override: int | None = None,
    markup_pct: float | None = None,
    note: str | None = None,
) -> int:
    product = products_core.get_product(conn, product_code)
    if product is None:
        raise ValueError(f"Unknown product code: {product_code}")

    price = unit_price_override
    if price is None:
        price = calc_unit_price(product["cost_price"], markup_pct if markup_pct is not None else PUBLIC_MARKUP_PCT)
    total = calc_line_total(price, qty)

    cur = conn.execute(
        """
        INSERT INTO invoice_lines
            (invoice_id, product_code, product_name_snapshot, unit_snapshot, qty, cost_price_snapshot, unit_price, line_total, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (invoice_id, product_code, product["name"], product["unit"], qty, product["cost_price"], price, total, note),
    )
    conn.commit()
    return cur.lastrowid


def add_custom_line(
    conn: sqlite3.Connection,
    invoice_id: int,
    name: str,
    unit_price: int,
    qty: float = 1,
    note: str | None = None,
) -> int:
    """A line with no catalog product behind it (request #4, lần 19) --
    e.g. a one-off service fee the owner types in by hand per order.
    product_code is blank: it's display-only (an Excel export column,
    see invoice_export.py), never a foreign key and never joined
    against products, so nothing else keys off it. cost_price_snapshot
    is 0, so the whole amount counts as profit -- same "Giá vốn" column
    in the editor stays editable on a draft if that's ever wrong for a
    specific fee."""
    total = calc_line_total(unit_price, qty)
    cur = conn.execute(
        """
        INSERT INTO invoice_lines
            (invoice_id, product_code, product_name_snapshot, unit_snapshot, qty, cost_price_snapshot, unit_price, line_total, note)
        VALUES (?, '', ?, NULL, ?, 0, ?, ?, ?)
        """,
        (invoice_id, name, qty, unit_price, total, note),
    )
    conn.commit()
    return cur.lastrowid


def update_line(
    conn: sqlite3.Connection,
    line_id: int,
    qty: float | None = None,
    unit_price_value: int | None = None,
    cost_price_value: float | None = None,
) -> None:
    """cost_price_value lets the owner correct a draft line's cost before
    finalizing -- e.g. the supplier's new price arrived after the line
    was added from a pasted Telegram order. Only call this on a draft:
    a finalized line's snapshot is meant to stay fixed (see module
    docstring), so the UI only exposes this while status == 'draft'."""
    row = conn.execute("SELECT qty, unit_price, cost_price_snapshot FROM invoice_lines WHERE id = ?", (line_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown invoice line id: {line_id}")
    new_qty = qty if qty is not None else row[0]
    new_price = unit_price_value if unit_price_value is not None else row[1]
    new_cost = cost_price_value if cost_price_value is not None else row[2]
    new_total = calc_line_total(new_price, new_qty)
    conn.execute(
        "UPDATE invoice_lines SET qty = ?, unit_price = ?, cost_price_snapshot = ?, line_total = ? WHERE id = ?",
        (new_qty, new_price, new_cost, new_total, line_id),
    )
    conn.commit()


def remove_line(conn: sqlite3.Connection, line_id: int) -> None:
    conn.execute("DELETE FROM invoice_lines WHERE id = ?", (line_id,))
    conn.commit()


def get_lines(conn: sqlite3.Connection, invoice_id: int) -> list[dict]:
    cols = ["id", "product_code", "product_name_snapshot", "unit_snapshot", "qty", "cost_price_snapshot", "unit_price", "line_total", "note"]
    rows = conn.execute(
        f"SELECT {', '.join(cols)} FROM invoice_lines WHERE invoice_id = ? ORDER BY id",
        (invoice_id,),
    ).fetchall()
    return [dict(zip(cols, row)) for row in rows]


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, customer_id, invoice_date, status, note, created_at FROM invoices WHERE id = ?",
        (invoice_id,),
    ).fetchone()
    if row is None:
        return None
    cols = ["id", "customer_id", "invoice_date", "status", "note", "created_at"]
    invoice = dict(zip(cols, row))
    invoice["lines"] = get_lines(conn, invoice_id)
    invoice["total"] = sum(line["line_total"] for line in invoice["lines"])
    return invoice


def list_invoices(conn: sqlite3.Connection, customer_id: int | None = None, status: str | None = None) -> list[dict]:
    sql = "SELECT id, customer_id, invoice_date, status, note, created_at FROM invoices WHERE 1=1"
    params: list = []
    if customer_id is not None:
        sql += " AND customer_id = ?"
        params.append(customer_id)
    if status is not None:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY invoice_date DESC, id DESC"
    cols = ["id", "customer_id", "invoice_date", "status", "note", "created_at"]
    return [dict(zip(cols, row)) for row in conn.execute(sql, params)]


def finalize_invoice(conn: sqlite3.Connection, invoice_id: int) -> None:
    lines = get_lines(conn, invoice_id)
    if not lines:
        raise ValueError("Cannot finalize an invoice with no lines")
    conn.execute("UPDATE invoices SET status = 'finalized' WHERE id = ?", (invoice_id,))
    conn.commit()


def cancel_invoice(conn: sqlite3.Connection, invoice_id: int) -> None:
    conn.execute("UPDATE invoices SET status = 'cancelled' WHERE id = ?", (invoice_id,))
    conn.commit()


def reopen_invoice(conn: sqlite3.Connection, invoice_id: int) -> None:
    """Finalized -> draft, so lines can be edited again. The invoice drops
    out of debt/profit while it's a draft (shop.core.summary only counts
    'finalized'); finalize it again when done."""
    conn.execute("UPDATE invoices SET status = 'draft' WHERE id = ? AND status = 'finalized'", (invoice_id,))
    conn.commit()


def delete_draft_invoice(conn: sqlite3.Connection, invoice_id: int) -> None:
    """Remove an empty draft (e.g. one created by mistake). Use
    cancel_invoice instead for anything with lines or history."""
    lines = get_lines(conn, invoice_id)
    if lines:
        raise ValueError("Only an empty draft can be deleted; use cancel_invoice otherwise.")
    conn.execute("DELETE FROM invoices WHERE id = ? AND status = 'draft'", (invoice_id,))
    conn.commit()


def invoice_profit(conn: sqlite3.Connection, invoice_id: int) -> int:
    """Profit = sum over lines of (line_total - cost at the snapshot cost
    price), each rounded the same way as the sale price."""
    from shop.core.pricing import round_rub

    total = 0
    for line in get_lines(conn, invoice_id):
        cost_total = round_rub(line["cost_price_snapshot"] * line["qty"])
        total += line["line_total"] - cost_total
    return total
