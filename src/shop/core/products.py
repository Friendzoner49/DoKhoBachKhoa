"""Product catalog: list/add/edit, with every cost change logged to
price_history so past invoices can always be explained.
"""
import json
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_COLS = [
    "code", "name", "unit", "category", "cost_price", "bulk_qty", "bulk_unit", "active", "image_filename",
    "in_stock", "sale_until", "channel_announced_at", "name_ru", "gallery_filenames", "description", "bulk_price_override",
]


def list_products(conn: sqlite3.Connection, active_only: bool = True) -> list[dict]:
    sql = f"SELECT {', '.join(_COLS)} FROM products"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY name COLLATE VNAME"
    return [dict(zip(_COLS, row)) for row in conn.execute(sql)]


def get_product(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute(
        f"SELECT {', '.join(_COLS)} FROM products WHERE code = ?",
        (code,),
    ).fetchone()
    if row is None:
        return None
    return dict(zip(_COLS, row))


def list_categories(conn: sqlite3.Connection) -> list[str]:
    """Distinct categories already in use, for populating an editable combo box."""
    rows = conn.execute(
        "SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category COLLATE VNAME"
    ).fetchall()
    return [row[0] for row in rows]


def upsert_product(
    conn: sqlite3.Connection,
    code: str,
    name: str,
    unit: str | None,
    cost_price: float,
    bulk_qty: float = 0,
    bulk_unit: str | None = None,
    category: str | None = None,
    active: bool = True,
    in_stock: bool | None = None,
    name_ru: str | None = None,
    source: str = "app",
) -> None:
    """Insert a new product, or update an existing one. Any cost_price
    change (including the first insert) is logged to price_history.

    category=None, in_stock=None, bulk_unit=None and name_ru=None leave
    an existing product's value untouched (rather than wiping it) --
    callers that want to actually clear/change them must do so
    explicitly (via set_category()/set_in_stock(), or by passing
    bulk_unit=""/name_ru="" here). This matters because import_xlsx
    --force, "Áp dụng giá mới" and some callers don't carry these fields
    at all, and silently resetting them would undo manual grouping, a
    "tạm hết hàng" flag, a pack label, or a Russian name typed in once
    through ProductDialog. A genuinely new product defaults to
    in_stock=True, bulk_unit="" and name_ru=""."""
    now = _now()
    existing_row = conn.execute(
        "SELECT cost_price, category, in_stock, bulk_unit, name_ru FROM products WHERE code = ?", (code,)
    ).fetchone()
    existing_cost = existing_row[0] if existing_row else None
    if category is None and existing_row is not None:
        category = existing_row[1]
    if in_stock is None:
        in_stock = bool(existing_row[2]) if existing_row is not None else True
    if bulk_unit is None:
        bulk_unit = existing_row[3] if existing_row is not None else ""
    if name_ru is None:
        name_ru = existing_row[4] if existing_row is not None else ""

    conn.execute(
        """
        INSERT INTO products (code, name, unit, category, cost_price, bulk_qty, bulk_unit, active, in_stock, name_ru, source_file, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            unit = excluded.unit,
            category = excluded.category,
            cost_price = excluded.cost_price,
            bulk_qty = excluded.bulk_qty,
            bulk_unit = excluded.bulk_unit,
            active = excluded.active,
            in_stock = excluded.in_stock,
            name_ru = excluded.name_ru,
            source_file = excluded.source_file,
            updated_at = excluded.updated_at
        """,
        (code, name, unit, category, cost_price, bulk_qty, bulk_unit, int(active), int(in_stock), name_ru, source, now),
    )

    if existing_cost is None or existing_cost != cost_price:
        conn.execute(
            "INSERT INTO price_history (product_code, cost_price, recorded_at, source_file, note) VALUES (?, ?, ?, ?, ?)",
            (code, cost_price, now, source, "initial" if existing_cost is None else "price changed"),
        )
    conn.commit()


def set_active(conn: sqlite3.Connection, code: str, active: bool) -> None:
    conn.execute("UPDATE products SET active = ?, updated_at = ? WHERE code = ?", (int(active), _now(), code))
    conn.commit()


def set_category(conn: sqlite3.Connection, code: str, category: str | None) -> None:
    conn.execute("UPDATE products SET category = ?, updated_at = ? WHERE code = ?", (category, _now(), code))
    conn.commit()


def set_bulk_price_override(conn: sqlite3.Connection, code: str, price: int | None) -> None:
    """The owner's fixed whole-bag SALE price exception (None removes it and goes
    back to the formula). A dedicated setter, not part of upsert_product, so
    price imports and supplier-invoice applies can never wipe it."""
    if price is not None and price <= 0:
        raise ValueError("Giá sỉ ngoại lệ phải lớn hơn 0 (hoặc bỏ ngoại lệ).")
    conn.execute(
        "UPDATE products SET bulk_price_override = ?, updated_at = ? WHERE code = ?",
        (None if price is None else int(price), _now(), code),
    )
    conn.commit()


def set_bulk_unit(conn: sqlite3.Connection, code: str, bulk_unit: str) -> None:
    conn.execute("UPDATE products SET bulk_unit = ?, updated_at = ? WHERE code = ?", (bulk_unit, _now(), code))
    conn.commit()


def set_in_stock(conn: sqlite3.Connection, code: str, in_stock: bool) -> None:
    conn.execute("UPDATE products SET in_stock = ?, updated_at = ? WHERE code = ?", (int(in_stock), _now(), code))
    conn.commit()


def set_image_filename(conn: sqlite3.Connection, code: str, image_filename: str | None) -> None:
    conn.execute("UPDATE products SET image_filename = ?, updated_at = ? WHERE code = ?", (image_filename, _now(), code))
    conn.commit()


def set_sale_until(conn: sqlite3.Connection, code: str, sale_until: str | None) -> None:
    """Managed outside upsert_product's INSERT/UPDATE, same reasoning as
    image_filename: a plain "pass the current value through" field
    whose caller (ProductDialog) always knows the intended end state
    explicitly, so there's no ambiguous "None means keep" case to
    design around here -- None always means "not a seasonal item"."""
    conn.execute("UPDATE products SET sale_until = ?, updated_at = ? WHERE code = ?", (sale_until, _now(), code))
    conn.commit()


def set_channel_announced(conn: sqlite3.Connection, code: str, announced_at: str | None) -> None:
    conn.execute("UPDATE products SET channel_announced_at = ? WHERE code = ?", (announced_at, code))
    conn.commit()


def gallery_list(product: dict) -> list[str]:
    """Parse a product's gallery_filenames column (a JSON array) into a
    plain list -- tolerant of the '' a pre-migration row would never
    actually have (column default is '[]') but defensive anyway, since
    hand-editing the DB is always possible."""
    raw = product.get("gallery_filenames") or "[]"
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


def set_gallery_filenames(conn: sqlite3.Connection, code: str, filenames: list[str]) -> None:
    """Special products only (lần 38, "Quà tặng") -- most products never
    call this, gallery_filenames stays '[]'. Order is display order on
    the website/app, first item shown first."""
    conn.execute(
        "UPDATE products SET gallery_filenames = ?, updated_at = ? WHERE code = ?",
        (json.dumps(filenames, ensure_ascii=False), _now(), code),
    )
    conn.commit()


def set_description(conn: sqlite3.Connection, code: str, description: str) -> None:
    conn.execute("UPDATE products SET description = ?, updated_at = ? WHERE code = ?", (description, _now(), code))
    conn.commit()


def price_history(conn: sqlite3.Connection, code: str) -> list[dict]:
    rows = conn.execute(
        "SELECT cost_price, recorded_at, source_file, note FROM price_history WHERE product_code = ? ORDER BY recorded_at",
        (code,),
    ).fetchall()
    cols = ["cost_price", "recorded_at", "source_file", "note"]
    return [dict(zip(cols, row)) for row in rows]
