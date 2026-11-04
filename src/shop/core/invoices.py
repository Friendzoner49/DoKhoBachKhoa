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
from shop.core.pricing import bulk_discount as calc_bulk_discount
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
    line_id = cur.lastrowid
    _resync_bulk_discount(conn, invoice_id, line_id, product, price, qty)
    return line_id


def _resync_bulk_discount(conn: sqlite3.Connection, invoice_id: int, main_line_id: int, product: dict, unit_price_value, qty: float) -> None:
    """Request "tôi muốn áp dụng thật chứ, tôi không buôn bán gian dối"
    (26/10/2026, lần 27): a product whose catalog bulk_qty the ordered
    qty has reached gets a linked discount line, not a discounted
    unit_price -- a separate line survives later cost/price edits on
    the main line (unit_price * qty = line_total stays true everywhere,
    see shop.core.pricing.bulk_discount), and shows the discount to the
    customer instead of quietly folding it into the unit price. Called
    after every add_line/update_line on a real catalog line (never for
    add_custom_line's own fee lines, which have no product) so the
    linked discount always matches the line's CURRENT qty/price, not
    just the qty it was first added with."""
    note_tag = f"bulk:{main_line_id}"
    existing = conn.execute(
        "SELECT id FROM invoice_lines WHERE invoice_id = ? AND note = ?", (invoice_id, note_tag)
    ).fetchone()
    discount = calc_bulk_discount(unit_price_value, qty, product["bulk_qty"])
    if discount <= 0:
        if existing:
            conn.execute("DELETE FROM invoice_lines WHERE id = ?", (existing[0],))
            conn.commit()
        return
    name = f"Chiết khấu sỉ 2% — {product['name']} ({qty:g}{' ' + product['unit'] if product['unit'] else ''})"
    if existing:
        conn.execute(
            "UPDATE invoice_lines SET product_name_snapshot = ?, unit_price = ?, line_total = ? WHERE id = ?",
            (name, -discount, -discount, existing[0]),
        )
        conn.commit()
    else:
        add_custom_line(conn, invoice_id, name=name, unit_price=-discount, qty=1, note=note_tag)


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
    row = conn.execute(
        "SELECT qty, unit_price, cost_price_snapshot, invoice_id, product_code FROM invoice_lines WHERE id = ?", (line_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown invoice line id: {line_id}")
    new_qty = qty if qty is not None else row[0]
    new_price = unit_price_value if unit_price_value is not None else row[1]
    new_cost = cost_price_value if cost_price_value is not None else row[2]
    invoice_id, product_code = row[3], row[4]
    new_total = calc_line_total(new_price, new_qty)
    conn.execute(
        "UPDATE invoice_lines SET qty = ?, unit_price = ?, cost_price_snapshot = ?, line_total = ? WHERE id = ?",
        (new_qty, new_price, new_cost, new_total, line_id),
    )
    conn.commit()
    if product_code:
        product = products_core.get_product(conn, product_code)
        if product is not None:
            _resync_bulk_discount(conn, invoice_id, line_id, product, new_price, new_qty)


def remove_line(conn: sqlite3.Connection, line_id: int) -> None:
    conn.execute("DELETE FROM invoice_lines WHERE note = ?", (f"bulk:{line_id}",))
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


def delete_invoice(conn: sqlite3.Connection, invoice_id: int) -> None:
    """Permanently remove a draft (empty or with lines) or a cancelled
    invoice -- 28/10/2026, giai đoạn kiểm thử. A 'finalized' invoice is
    refused -- it's already
    counted in a customer's real debt/profit history (shop.core.summary),
    so deleting it would silently rewrite numbers the owner already
    relied on; "Hủy" (cancel_invoice) is the only way to back one out,
    same as before.

    Same FK trap online_orders.convert_to_invoice's docstring already
    flags for an empty invoice: online_orders.linked_invoice_id has no
    ON DELETE, so a row still pointing at this invoice must be unlinked
    FIRST or this blows up with "FOREIGN KEY constraint failed". Reset
    to 'cho_xu_ly' (not just unlinked) so the order is billable again
    instead of stuck looking "already invoiced" with nothing to show
    for it -- plain SQL against online_orders here (no import of that
    module) to avoid a circular import, since online_orders.py already
    imports this module as invoices_core."""
    row = conn.execute("SELECT status FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if row is None:
        raise ValueError(f"No such invoice: {invoice_id}")
    status = row[0]
    if status not in ("draft", "cancelled"):
        raise ValueError("Chỉ xóa được hóa đơn nháp hoặc đã hủy -- hóa đơn đã hoàn tất chỉ có thể \"Hủy\".")

    conn.execute(
        "UPDATE online_orders SET status = 'cho_xu_ly', linked_invoice_id = NULL WHERE linked_invoice_id = ?",
        (invoice_id,),
    )
    conn.execute("DELETE FROM invoice_lines WHERE invoice_id = ?", (invoice_id,))
    conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
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
