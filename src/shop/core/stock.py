"""Limited portions ("số suất có hạn") of a pre-order dish.

The app owns the limit and counts what is already taken; the bot subtracts
only the orders newer than the published cut-off (bot/src/stock.js), so an
order is never counted twice and never missed between two publishes.
"""
import sqlite3
from datetime import date, datetime, time, timezone

from shop.core.products import deadline_passed


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def set_stock_limit(
    conn: sqlite3.Connection,
    code: str,
    limit: int | None,
    previous: dict | None = None,
    now: datetime | None = None,
) -> None:
    """Set (or with None remove) the number of portions on sale.

    A new sale round starts (counting from 00:00 today) when the limit is
    switched on, or when a dish whose deadline had passed gets a new one
    (`previous` is the product as it was before this edit).
    Changing the number or extending a still-open deadline keeps counting.
    """
    if limit is not None and limit <= 0:
        raise ValueError("Số suất phải lớn hơn 0 (hoặc để trống nếu không giới hạn).")
    row = conn.execute(
        "SELECT stock_limit, stock_since, sale_until, sale_until_time FROM products WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown product code: {code}")
    old_limit, since, sale_until, sale_until_time = row
    now = now or datetime.now().astimezone()
    today = now.date()
    reopened = (
        previous is not None
        and deadline_passed(previous, now)
        and (sale_until, sale_until_time) != (previous.get("sale_until"), previous.get("sale_until_time"))
    )
    if limit is None:
        since = None
    elif old_limit is None or since is None or reopened:
        start = datetime.combine(today, time.min).astimezone(timezone.utc)
        since = start.isoformat(timespec="seconds")
    conn.execute(
        "UPDATE products SET stock_limit = ?, stock_since = ?, updated_at = ? WHERE code = ?",
        (limit, since, datetime.now(timezone.utc).isoformat(timespec="seconds"), code),
    )
    conn.commit()


def sold_qty(conn: sqlite3.Connection, code: str, since: str) -> float:
    """Portions taken since `since`: online orders that are not cancelled (lines
    not struck out), plus invoices typed by hand. An invoice made FROM an
    online order is skipped, that order is already counted."""
    online = conn.execute(
        """
        SELECT COALESCE(SUM(l.qty), 0) FROM online_order_lines l
        JOIN online_orders o ON o.id = l.online_order_id
        WHERE l.code = ? AND l.excluded = 0 AND o.status != 'da_huy'
          AND julianday(o.placed_at) >= julianday(?)
        """,
        (code, since),
    ).fetchone()[0]
    manual = conn.execute(
        """
        SELECT COALESCE(SUM(l.qty), 0) FROM invoice_lines l
        JOIN invoices i ON i.id = l.invoice_id
        WHERE l.product_code = ? AND i.status != 'cancelled'
          AND i.id NOT IN (SELECT linked_invoice_id FROM online_orders WHERE linked_invoice_id IS NOT NULL)
          AND julianday(i.created_at) >= julianday(?)
        """,
        (code, since),
    ).fetchone()[0]
    return online + manual


def remaining(conn: sqlite3.Connection, product: dict) -> int | None:
    """Portions left, or None when the product has no limit."""
    if not product.get("stock_limit") or not product.get("stock_since"):
        return None
    return max(0, int(product["stock_limit"] - sold_qty(conn, product["code"], product["stock_since"])))


def order_cutoff_ms(conn: sqlite3.Connection, since: str) -> int:
    """Bot orders newer than this (ms) are not in remaining() yet. Only a time
    is published, never the order key itself (it holds a Telegram chat id)."""
    from shop.core.online_orders import _sync_floor_ms

    marks = [_ms(since), _sync_floor_ms(conn) or 0]
    last = conn.execute("SELECT MAX(source_key) FROM online_orders WHERE source_key LIKE 'sync:%'").fetchone()[0]
    if last:
        head = last.split(":", 1)[1].split("-", 1)[0]
        if head.isdigit():
            marks.append(int(head))
    return max(marks)
