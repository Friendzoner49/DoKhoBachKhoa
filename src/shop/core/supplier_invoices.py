"""Importing the (single) supplier's delivery invoices: log what was
received, compare its per-catalog-unit price against the current cost,
and apply confirmed cost changes. Every confirmed name match is
remembered (supplier_aliases) so the next invoice from the same
supplier needs less manual re-matching -- there's only ever one
supplier in this shop, so aliases aren't scoped to one.

Matching is deliberately not fully automatic: a supplier invoice writes
raw, often abbreviated/romanized names ("Banh Da Nem (Thanh Thuy)")
against the catalog's proper Vietnamese names ("Bánh Đa Nem Tròn Hà Nội
200gr"), and the unit on the invoice (e.g. "кор (30 шт)", a case of 30)
is often not the catalog's unit -- getting either wrong corrupts a real
cost_price, so every line needs the user's confirmation before
line_cost_preview() is trusted and apply_invoice() writes it.
"""
import base64
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from shop.core.products import get_product, list_products, upsert_product
from shop.core.text import normalize


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_invoice(
    conn: sqlite3.Connection,
    invoice_number: str | None = None,
    invoice_date: str | None = None,
    photo_filename: str | None = None,
    source_key: str | None = None,
    note: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO supplier_invoices (invoice_number, invoice_date, photo_filename, source_key, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (invoice_number, invoice_date, photo_filename, source_key, note, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, invoice_number, invoice_date, photo_filename, total_amount, paid, applied_at, created_at, note, order_batch_id "
        "FROM supplier_invoices WHERE id = ?",
        (invoice_id,),
    ).fetchone()
    if row is None:
        return None
    cols = ["id", "invoice_number", "invoice_date", "photo_filename", "total_amount", "paid", "applied_at", "created_at", "note", "order_batch_id"]
    invoice = dict(zip(cols, row))
    invoice["lines"] = list_lines(conn, invoice_id)
    return invoice


def list_invoices(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, invoice_number, invoice_date, photo_filename, total_amount, paid, applied_at, created_at, note, order_batch_id "
        "FROM supplier_invoices ORDER BY COALESCE(invoice_date, created_at) DESC, id DESC"
    ).fetchall()
    cols = ["id", "invoice_number", "invoice_date", "photo_filename", "total_amount", "paid", "applied_at", "created_at", "note", "order_batch_id"]
    return [dict(zip(cols, row)) for row in rows]


def set_total_amount(conn: sqlite3.Connection, invoice_id: int, total_amount: int) -> None:
    conn.execute("UPDATE supplier_invoices SET total_amount = ? WHERE id = ?", (total_amount, invoice_id))
    conn.commit()


def set_paid(conn: sqlite3.Connection, invoice_id: int, paid: bool) -> None:
    conn.execute("UPDATE supplier_invoices SET paid = ? WHERE id = ?", (int(paid), invoice_id))
    conn.commit()


def total_unpaid(conn: sqlite3.Connection) -> int:
    """What's currently owed to the supplier -- the other half of the
    dashboard's "pay supplier or collect from customers" decision. Falls
    back to summing that invoice's own lines when the header total was
    never typed in (total_amount left at 0), so an invoice entered line
    by line without ever filling the header field doesn't silently
    count as 0 owed."""
    total = 0
    for invoice_id, total_amount in conn.execute(
        "SELECT id, total_amount FROM supplier_invoices WHERE paid = 0"
    ).fetchall():
        if total_amount:
            total += total_amount
        else:
            total += conn.execute(
                "SELECT COALESCE(SUM(raw_line_total), 0) FROM supplier_invoice_lines WHERE supplier_invoice_id = ?",
                (invoice_id,),
            ).fetchone()[0]
    return round(total)


def add_line(
    conn: sqlite3.Connection,
    supplier_invoice_id: int,
    raw_name: str,
    raw_qty: float | None,
    raw_unit: str | None,
    raw_unit_price: float | None,
    matched_code: str | None = None,
    unit_conversion: float = 1.0,
) -> int:
    raw_line_total = round(raw_qty * raw_unit_price, 2) if raw_qty is not None and raw_unit_price is not None else None
    cur = conn.execute(
        """
        INSERT INTO supplier_invoice_lines
            (supplier_invoice_id, raw_name, raw_qty, raw_unit, raw_unit_price, raw_line_total, matched_code, unit_conversion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (supplier_invoice_id, raw_name, raw_qty, raw_unit, raw_unit_price, raw_line_total, matched_code, unit_conversion),
    )
    conn.commit()
    return cur.lastrowid


_UNSET = object()  # distinguishes "caller didn't pass this" from "caller passed None to clear it"


def update_line(
    conn: sqlite3.Connection,
    line_id: int,
    raw_name=_UNSET,
    raw_qty=_UNSET,
    raw_unit=_UNSET,
    raw_unit_price=_UNSET,
    matched_code=_UNSET,
    unit_conversion=_UNSET,
) -> None:
    """Partial update: any argument left at its default is untouched.
    Pass matched_code=None explicitly to un-match a line -- that's a
    real, meaningful state (the UI's "clear the code cell" action), not
    "no change", which a plain `= None` default could not tell apart."""
    current = conn.execute(
        "SELECT raw_name, raw_qty, raw_unit, raw_unit_price, matched_code, unit_conversion "
        "FROM supplier_invoice_lines WHERE id = ?",
        (line_id,),
    ).fetchone()
    if current is None:
        raise ValueError(f"no such supplier invoice line: {line_id}")
    cur_name, cur_qty, cur_unit, cur_price, cur_code, cur_conv = current
    raw_name = cur_name if raw_name is _UNSET else raw_name
    raw_qty = cur_qty if raw_qty is _UNSET else raw_qty
    raw_unit = cur_unit if raw_unit is _UNSET else raw_unit
    raw_unit_price = cur_price if raw_unit_price is _UNSET else raw_unit_price
    matched_code = cur_code if matched_code is _UNSET else matched_code
    unit_conversion = cur_conv if unit_conversion is _UNSET else unit_conversion
    raw_line_total = round(raw_qty * raw_unit_price, 2) if raw_qty is not None and raw_unit_price is not None else None

    conn.execute(
        """
        UPDATE supplier_invoice_lines
        SET raw_name = ?, raw_qty = ?, raw_unit = ?, raw_unit_price = ?, raw_line_total = ?,
            matched_code = ?, unit_conversion = ?
        WHERE id = ?
        """,
        (raw_name, raw_qty, raw_unit, raw_unit_price, raw_line_total, matched_code, unit_conversion, line_id),
    )
    conn.commit()


def remove_line(conn: sqlite3.Connection, line_id: int) -> None:
    conn.execute("DELETE FROM supplier_invoice_lines WHERE id = ?", (line_id,))
    conn.commit()


def list_lines(conn: sqlite3.Connection, supplier_invoice_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, raw_name, raw_qty, raw_unit, raw_unit_price, raw_line_total,
               matched_code, unit_conversion, cost_price_before, cost_price_after, note
        FROM supplier_invoice_lines
        WHERE supplier_invoice_id = ?
        ORDER BY id
        """,
        (supplier_invoice_id,),
    ).fetchall()
    cols = [
        "id", "raw_name", "raw_qty", "raw_unit", "raw_unit_price", "raw_line_total",
        "matched_code", "unit_conversion", "cost_price_before", "cost_price_after", "note",
    ]
    return [dict(zip(cols, row)) for row in rows]


def get_alias(conn: sqlite3.Connection, raw_name: str) -> dict | None:
    row = conn.execute(
        "SELECT product_code, unit_conversion FROM supplier_aliases WHERE raw_name_normalized = ?",
        (normalize(raw_name),),
    ).fetchone()
    if row is None:
        return None
    return {"code": row[0], "unit_conversion": row[1]}


def save_alias(conn: sqlite3.Connection, raw_name: str, code: str, unit_conversion: float) -> None:
    conn.execute(
        """
        INSERT INTO supplier_aliases (raw_name_normalized, product_code, unit_conversion)
        VALUES (?, ?, ?)
        ON CONFLICT(raw_name_normalized) DO UPDATE SET
            product_code = excluded.product_code,
            unit_conversion = excluded.unit_conversion
        """,
        (normalize(raw_name), code, unit_conversion),
    )
    conn.commit()


def suggest_matches(conn: sqlite3.Connection, raw_name: str, limit: int = 5) -> list[dict]:
    """A remembered alias always comes first (score=999: the user already
    confirmed this exact raw name once). Otherwise, rank catalog products
    by how many normalized words they share with raw_name -- supplier
    lines embed the Vietnamese name as a substring inside a longer
    Russian/packaging description, so word overlap is a decent signal
    even though the strings are never equal."""
    results = []
    alias = get_alias(conn, raw_name)
    if alias:
        product = get_product(conn, alias["code"])
        if product:
            results.append(
                {"code": product["code"], "name": product["name"], "score": 999, "unit_conversion": alias["unit_conversion"]}
            )

    raw_tokens = set(normalize(raw_name).split())
    scored = []
    if raw_tokens:
        for p in list_products(conn, active_only=False):
            if p["code"] == (results[0]["code"] if results else None):
                continue
            overlap = len(raw_tokens & set(normalize(p["name"]).split()))
            if overlap:
                scored.append((overlap, p))
    scored.sort(key=lambda pair: -pair[0])
    for _overlap, p in scored[: max(0, limit - len(results))]:
        results.append({"code": p["code"], "name": p["name"], "score": _overlap, "unit_conversion": 1.0})
    return results[:limit]


def known_lines(conn: sqlite3.Connection) -> list[dict]:
    """Every product ever matched to a supplier-invoice line, each shown
    with the MOST RECENT raw name/qty/unit/conversion it was recorded
    under (not tied to any single invoice) plus order_count (how many
    DISTINCT past invoices contained it, most-recurring first -- same
    "rank by how many separate orders, not raw quantity" idea as
    bot/src/orderHistory.js's topCodes). Powers the "Thêm mặt hàng quen
    thuộc" picker (lần 22): with only one supplier (CLAUDE.md section
    1), the SAME product list recurs across deliveries, so a NEW
    invoice can start from "what we usually buy" instead of a blank
    table.

    This exists BECAUSE real-world testing showed Tesseract cannot
    reliably read these hand-stamped, photographed invoice TABLES (see
    CLAUDE.md lần 22) -- trying to auto-fill from OCR'd text would
    silently plant wrong names/quantities. This is the reliable
    alternative: built from the owner's own PAST CONFIRMED matches, not
    a guess from pixels.

    Deliberately just DATA, not a bulk-insert: the caller (a checklist
    dialog) must let the owner TICK only the items actually on this
    delivery's photo and type each quantity there -- blindly inserting
    every product ever matched would, with only one supplier, grow
    toward the whole catalog, leaving dozens of zero-price "phantom"
    lines per invoice that the owner would have to delete one by one,
    and that a later per-invoice "what arrived" feature could
    misread as real deliveries.

    raw_unit_price is deliberately NOT returned here -- the price for
    THIS delivery must always come from THIS invoice's photo, never
    carried over from a previous one."""
    latest = conn.execute(
        """
        SELECT sil.matched_code, sil.raw_name, sil.raw_qty, sil.raw_unit, sil.unit_conversion
        FROM supplier_invoice_lines sil
        WHERE sil.matched_code IS NOT NULL
          AND sil.matched_code IN (SELECT code FROM products WHERE active = 1)
          AND sil.id = (
              SELECT MAX(id) FROM supplier_invoice_lines sil2 WHERE sil2.matched_code = sil.matched_code
          )
        """
    ).fetchall()
    counts = dict(
        conn.execute(
            """
            SELECT matched_code, COUNT(DISTINCT supplier_invoice_id)
            FROM supplier_invoice_lines
            WHERE matched_code IS NOT NULL
            GROUP BY matched_code
            """
        ).fetchall()
    )
    cols = ["matched_code", "raw_name", "raw_qty", "raw_unit", "unit_conversion"]
    rows = [dict(zip(cols, row)) for row in latest]
    for row in rows:
        row["order_count"] = counts.get(row["matched_code"], 0)
    rows.sort(key=lambda r: (-r["order_count"], (r["raw_name"] or "").lower()))
    return rows


def line_cost_preview(conn: sqlite3.Connection, line: dict) -> dict:
    """The per-catalog-unit cost this line implies, versus the product's
    current cost_price. None/None if the line isn't matched yet or is
    missing a price."""
    if not line.get("matched_code") or line.get("raw_unit_price") is None:
        return {"old_cost": None, "new_cost": None, "delta_pct": None}
    product = get_product(conn, line["matched_code"])
    old_cost = product["cost_price"] if product else None
    conversion = line.get("unit_conversion") or 1.0
    new_cost = line["raw_unit_price"] / conversion if conversion else None
    delta_pct = None
    if old_cost is not None and new_cost is not None and old_cost != 0:
        delta_pct = (new_cost - old_cost) / old_cost * 100
    return {"old_cost": old_cost, "new_cost": new_cost, "delta_pct": delta_pct}


def apply_invoice(conn: sqlite3.Connection, supplier_invoice_id: int) -> list[dict]:
    """Push every matched line's implied cost into the catalog (logged to
    price_history via upsert_product), remember the alias, and mark the
    invoice applied. Returns the list of lines that were actually
    changed, for a confirmation summary. Safe to call again -- an
    already-applied line whose cost hasn't changed is simply skipped,
    and a line added after the first apply still gets picked up."""
    invoice = get_invoice(conn, supplier_invoice_id)
    if invoice is None:
        raise ValueError(f"no such supplier invoice: {supplier_invoice_id}")

    applied = []
    for line in invoice["lines"]:
        if not line["matched_code"]:
            continue
        preview = line_cost_preview(conn, line)
        if preview["new_cost"] is None:
            continue
        product = get_product(conn, line["matched_code"])
        if product is None:
            continue
        upsert_product(
            conn,
            code=product["code"],
            name=product["name"],
            unit=product["unit"],
            cost_price=preview["new_cost"],
            bulk_qty=product["bulk_qty"],
            source=f"supplier-invoice-{invoice['invoice_number'] or supplier_invoice_id}",
        )
        save_alias(conn, line["raw_name"], line["matched_code"], line["unit_conversion"])
        conn.execute(
            "UPDATE supplier_invoice_lines SET cost_price_before = ?, cost_price_after = ? WHERE id = ?",
            (preview["old_cost"], preview["new_cost"], line["id"]),
        )
        applied.append({**line, **preview})

    conn.execute("UPDATE supplier_invoices SET applied_at = ? WHERE id = ?", (_now(), supplier_invoice_id))
    conn.commit()
    return applied


# ---- Syncing photos sent to the Telegram group command ("/hangve", lần 20) ----
# Mirrors shop.core.online_orders.sync_from_bot's shape closely -- same
# Worker, same KV-eventual-consistency backoff margin, same Cloudflare
# edge User-Agent workaround -- because it's the exact same kind of
# operation (admin app pulls new records from the bot via GET + a
# header secret) against a sibling endpoint, not a coincidence.
from shop.core.online_orders import SyncError, _sync_floor_ms  # noqa: E402 -- see module docstring above

_PHOTO_SYNC_BACKOFF_MS = 10 * 60 * 1000


def _photo_sync_floor(conn: sqlite3.Connection) -> str | None:
    # Same reset floor shop.core.reset writes via online_orders.set_sync_floor
    # (one shared millisecond timestamp), but built with THIS module's own
    # "photo:" prefix -- comparing it against online_orders' "sync:"-
    # prefixed keys (or vice versa) would sort wrong lexicographically.
    # See set_sync_floor's docstring.
    ms = _sync_floor_ms(conn)
    return f"photo:{ms:013d}" if ms is not None else None


def _last_photo_source_key(conn: sqlite3.Connection) -> str | None:
    max_key = conn.execute("SELECT MAX(source_key) FROM supplier_invoices WHERE source_key IS NOT NULL").fetchone()[0]
    backed_off = None
    if max_key:
        try:
            prefix, rest = max_key.split(":", 1)
            ts = int(rest.split("-", 1)[0]) - _PHOTO_SYNC_BACKOFF_MS
            backed_off = f"{prefix}:{max(ts, 0):013d}"
        except (ValueError, IndexError):
            backed_off = max_key

    floor = _photo_sync_floor(conn)
    if floor and backed_off:
        return max(floor, backed_off)
    return floor or backed_off


def sync_photos_from_bot(
    conn: sqlite3.Connection, worker_url: str, sync_secret: str, photos_dir: Path, timeout: float = 20.0
) -> int:
    """Pulls new supplier-invoice photos sent as "/hangve <ghi chú>" in
    the Telegram group (see bot/src/handlers.js), each one becoming its
    own draft supplier_invoices row (source_key UNIQUE, so a re-pull is
    silently skipped, not duplicated) with the photo already attached --
    ready to open in SupplierInvoiceDialog exactly like one picked by
    hand via "Chọn ảnh…". Never applies anything to products -- only
    apply_invoice() does that, and only once a human opens the invoice
    and clicks "Áp dụng giá mới vào danh mục". Returns how many were
    newly inserted."""
    if not worker_url or not sync_secret:
        raise SyncError("Chưa cài đặt đồng bộ: cần nhập Worker URL và Mã đồng bộ trước (xem bot/README.md).")

    since = _last_photo_source_key(conn)
    url = worker_url.rstrip("/") + "/sync/photos"
    if since:
        url += f"?since={quote(since)}"

    req = urllib.request.Request(
        url, headers={"X-Sync-Secret": sync_secret, "User-Agent": "ShopApp-OnlineOrdersSync/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise SyncError("Mã đồng bộ không đúng. Kiểm tra lại Mã đồng bộ trong app và SYNC_SECRET trên Cloudflare.") from e
        raise SyncError(f"Bot trả về lỗi (HTTP {e.code}). Thử lại sau.") from e
    except urllib.error.URLError as e:
        raise SyncError(
            "Không kết nối được tới bot. Kiểm tra mạng (có thể cần VPN nếu đang ở Nga) rồi thử lại."
        ) from e
    except (TimeoutError, OSError) as e:
        raise SyncError("Kết nối tới bot quá lâu, thử lại sau.") from e
    except ValueError as e:
        # A 200 response that isn't valid JSON -- e.g. this Worker build
        # doesn't have /sync/photos yet and the catch-all "OK" text
        # response answered instead. Same gotcha as online_orders.sync_from_bot.
        raise SyncError("Bot chưa hỗ trợ đồng bộ ảnh hóa đơn -- cần deploy lại Worker (xem bot/README.md).") from e

    inserted = 0
    photos_dir.mkdir(parents=True, exist_ok=True)
    for photo in data.get("photos", []):
        if _insert_photo(conn, photo, photos_dir):
            inserted += 1
    return inserted


def _insert_photo(conn: sqlite3.Connection, photo: dict, photos_dir: Path) -> bool:
    key = photo["key"]
    floor = _photo_sync_floor(conn)
    if floor and key <= floor:
        # Pre-reset photo the Worker returned anyway -- second line of
        # defense, same spirit as online_orders._insert_online_order.
        return False
    if conn.execute("SELECT 1 FROM supplier_invoices WHERE source_key = ?", (key,)).fetchone():
        return False  # already synced before
    invoice_id = create_invoice(conn, source_key=key, note=photo.get("note") or None)
    data_b64 = photo.get("data")
    if data_b64:
        filename = f"{invoice_id}-telegram.jpg"
        (photos_dir / filename).write_bytes(base64.b64decode(data_b64))
        conn.execute("UPDATE supplier_invoices SET photo_filename = ? WHERE id = ?", (filename, invoice_id))
        conn.commit()
    # No photo bytes in the payload (shouldn't happen, but never silently
    # drop the record) -- the draft still shows up with its note, the
    # owner can "Chọn ảnh…" by hand if needed.
    return True
