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
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from shop.core.products import get_product, list_products, upsert_product
from shop.core.text import normalize


def render_pdf_first_page(pdf_path: Path, dest_png: Path, max_side: int = 3000) -> int:
    """Renders page 1 of a scanned-invoice PDF to a PNG (pypdfium2, pure
    wheel -- nothing extra for the user to install). The PDF itself is
    only read, never modified. Returns the PDF's page count so the caller
    can warn when later pages are ignored."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page_count = len(pdf)
        if page_count == 0:
            raise ValueError("File PDF không có trang nào.")
        page = pdf[0]
        width, height = page.get_size()
        scale = min(1.5, max_side / max(width, height))  # 1.0 = 72 dpi
        page.render(scale=scale).to_pil().convert("RGB").save(dest_png)
    finally:
        pdf.close()
    return page_count


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
    raw_name_ru: str | None = None,
) -> int:
    """raw_name_ru (28/10/2026): the Russian name as read straight off the
    photo by the AI vision OCR, if any -- reference-only, never used for
    matching (see 011_supplier_invoice_lines_ru.sql for why: it's a
    different alphabet from the Latin transliteration raw_name/
    supplier_aliases already match on)."""
    raw_line_total = round(raw_qty * raw_unit_price, 2) if raw_qty is not None and raw_unit_price is not None else None
    cur = conn.execute(
        """
        INSERT INTO supplier_invoice_lines
            (supplier_invoice_id, raw_name, raw_qty, raw_unit, raw_unit_price, raw_line_total, matched_code, unit_conversion, raw_name_ru)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (supplier_invoice_id, raw_name, raw_qty, raw_unit, raw_unit_price, raw_line_total, matched_code, unit_conversion, raw_name_ru),
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
    if matched_code:
        # Every confirmed match is remembered right away (both printed names), so the
        # next AI-read invoice fills this product in by itself.
        ru = conn.execute("SELECT raw_name_ru FROM supplier_invoice_lines WHERE id = ?", (line_id,)).fetchone()[0]
        learn_alias(
            conn, [raw_name, ru], matched_code,
            _line_conversion(conn, {"unit_conversion": unit_conversion, "matched_code": matched_code, "raw_unit_price": raw_unit_price}),
        )


def remove_line(conn: sqlite3.Connection, line_id: int) -> None:
    conn.execute("DELETE FROM supplier_invoice_lines WHERE id = ?", (line_id,))
    conn.commit()


def list_lines(conn: sqlite3.Connection, supplier_invoice_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, raw_name, raw_qty, raw_unit, raw_unit_price, raw_line_total,
               matched_code, unit_conversion, cost_price_before, cost_price_after, note, raw_name_ru
        FROM supplier_invoice_lines
        WHERE supplier_invoice_id = ?
        ORDER BY id
        """,
        (supplier_invoice_id,),
    ).fetchall()
    cols = [
        "id", "raw_name", "raw_qty", "raw_unit", "raw_unit_price", "raw_line_total",
        "matched_code", "unit_conversion", "cost_price_before", "cost_price_after", "note", "raw_name_ru",
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
from shop.core.online_orders import SyncError, _sync_floor_ms, fetch_sync_json  # noqa: E402 -- see module docstring above

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
    # A non-JSON 200 here usually means this Worker build doesn't have
    # /sync/photos yet and the catch-all "OK" text response answered.
    data = fetch_sync_json(
        worker_url, sync_secret, "/sync/photos", _last_photo_source_key(conn), timeout,
        "Bot chưa hỗ trợ đồng bộ ảnh hóa đơn -- cần deploy lại Worker (xem bot/README.md).",
    )

    inserted = 0
    photos_dir.mkdir(parents=True, exist_ok=True)
    for photo in data.get("photos", []):
        if _insert_photo(conn, photo, photos_dir, worker_url, sync_secret):
            inserted += 1
    return inserted


def _worker_request(worker_url: str, sync_secret: str, path: str, body: dict | None = None, timeout: float = 60.0) -> bytes:
    """GET (or POST json when body is given) to the Worker with the shared secret.
    Raises OSError-family/URLError on any failure -- callers decide what is fatal."""
    import json
    import urllib.request

    req = urllib.request.Request(
        worker_url.rstrip("/") + path,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={
            "X-Sync-Secret": sync_secret,
            "User-Agent": "ShopApp-OnlineOrdersSync/1.0",  # see fetch_sync_json: Cloudflare blocks the default UA
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _insert_pdf_photo(conn, invoice_id: int, photo: dict, photos_dir: Path, worker_url: str, sync_secret: str) -> None:
    """A "/hangve" PDF scan: download the raw PDF, keep it untouched next to the
    rendered PNG (the PNG is what the invoice shows/OCRs), then post the sharp PNG
    back into the Telegram group so the owner can save it to the phone's album.
    Failures never lose the invoice row -- they are noted on it instead."""
    import base64 as b64
    from urllib.parse import quote

    problems = []
    try:
        pdf_bytes = _worker_request(worker_url, sync_secret, "/sync/photo-blob?key=" + quote(photo["blob"], safe=""))
        pdf_path = photos_dir / f"{invoice_id}-telegram.pdf"
        pdf_path.write_bytes(pdf_bytes)
        png_name = f"{invoice_id}-telegram.png"
        render_pdf_first_page(pdf_path, photos_dir / png_name)
        conn.execute("UPDATE supplier_invoices SET photo_filename = ? WHERE id = ?", (png_name, invoice_id))
    except Exception as exc:  # noqa: BLE001 -- network/PDF errors alike: keep the draft, say why
        problems.append(f"không tải/đổi được PDF ({exc})")
        png_name = None
    if png_name and photo.get("reply_chat_id"):
        try:
            _worker_request(
                worker_url,
                sync_secret,
                "/hangve/reply",
                {
                    "chat_id": photo["reply_chat_id"],
                    "reply_to_message_id": photo.get("reply_to_message_id"),
                    "imageBase64": b64.b64encode((photos_dir / png_name).read_bytes()).decode("ascii"),
                    "filename": f"hoa-don-{invoice_id}.png",
                    "caption": "Ảnh nét từ file PDF vừa gửi (lưu vào album nhé).",
                },
            )
        except Exception as exc:  # noqa: BLE001
            problems.append(f"chưa gửi được ảnh nét lại Telegram ({exc})")
    if problems:
        note = (photo.get("note") or "").strip()
        conn.execute(
            "UPDATE supplier_invoices SET note = ? WHERE id = ?",
            ((note + " | " if note else "") + "⚠ " + "; ".join(problems), invoice_id),
        )
    conn.commit()


def _insert_photo(conn: sqlite3.Connection, photo: dict, photos_dir: Path, worker_url: str = "", sync_secret: str = "") -> bool:
    key = photo["key"]
    floor = _photo_sync_floor(conn)
    if floor and key <= floor:
        # Pre-reset photo the Worker returned anyway -- second line of
        # defense, same spirit as online_orders._insert_online_order.
        return False
    if key in _deleted_photo_keys(conn):
        return False  # the owner deleted this one -- never bring it back
    if conn.execute("SELECT 1 FROM supplier_invoices WHERE source_key = ?", (key,)).fetchone():
        return False  # already synced before
    invoice_id = create_invoice(conn, source_key=key, note=photo.get("note") or None)
    if photo.get("blob"):
        _insert_pdf_photo(conn, invoice_id, photo, photos_dir, worker_url, sync_secret)
        return True
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


# ---- Wholesale (bao/thùng) prices on the supplier invoice ----


def suggest_wholesale_conversion(conn: sqlite3.Connection, code: str, raw_unit_price: float | None) -> float:
    """The catalog cost is per retail unit (kg, gói...), but the supplier
    invoice often prices a whole bao/thùng. For a product with a bulk size
    (bulk_qty > 1), if dividing the invoice price by that size lands closer
    to the current cost than the raw price does, the invoice price is the
    WHOLESALE price -> suggest conversion = bulk_qty. 1.0 when unsure (e.g.
    a carton product the supplier still prices per piece), so the owner can
    always see and edit the "Quy đổi" cell."""
    if not raw_unit_price or raw_unit_price <= 0:
        return 1.0
    product = get_product(conn, code)
    if product is None or not product["bulk_qty"] or product["bulk_qty"] <= 1 or not product["cost_price"]:
        return 1.0
    import math

    old = product["cost_price"]
    raw_gap = abs(math.log(raw_unit_price / old))
    bulk_gap = abs(math.log(raw_unit_price / product["bulk_qty"] / old))
    return float(product["bulk_qty"]) if bulk_gap < raw_gap else 1.0


def auto_convert_wholesale(conn: sqlite3.Connection, supplier_invoice_id: int) -> list[dict]:
    """Applies suggest_wholesale_conversion to every matched line still at
    conversion 1 (a conversion the owner already typed is never touched).
    Returns the changed lines for a confirmation message."""
    changed = []
    for line in list_lines(conn, supplier_invoice_id):
        if not line["matched_code"] or (line["unit_conversion"] or 1.0) != 1.0:
            continue
        suggestion = suggest_wholesale_conversion(conn, line["matched_code"], line["raw_unit_price"])
        if suggestion != 1.0:
            update_line(conn, line["id"], unit_conversion=suggestion)
            changed.append({**line, "unit_conversion": suggestion})
    return changed


# ---- Learning from confirmed matches, so later AI-read invoices match by themselves ----
# The AI re-reads the same product with slightly different spelling every
# time, so an exact-name alias alone rarely hits again. Every match the
# owner confirms is therefore remembered under BOTH names printed on the
# invoice (Latin and Russian), and find_known_match() also accepts a close
# (not identical) wording -- but only when it is clearly closer to ONE
# remembered product than to any other.

_FUZZY_MIN = 0.6  # share of words that match (allowing small misspellings)
_FUZZY_MARGIN = 0.15  # best must beat the runner-up (a different product) by this much


def _words(text: str) -> set[str]:
    import re

    return set(re.findall(r"\w+", normalize(text or "")))


def _soft_overlap(a: set[str], b: set[str]) -> float:
    """Share of words that have a counterpart in the other set, where a
    counterpart may be spelled slightly differently (the AI misreads a
    letter or two between photos: "asecock" vs "acecook")."""
    from difflib import SequenceMatcher

    small, large = (a, b) if len(a) <= len(b) else (b, a)
    free = set(large)
    matched = 0
    for word in small:
        best = max(free, key=lambda other: SequenceMatcher(None, word, other).ratio(), default=None)
        if best is not None and SequenceMatcher(None, word, best).ratio() >= 0.75:
            matched += 1
            free.discard(best)
    return matched / max(len(a), len(b))



def learn_alias(conn: sqlite3.Connection, names: list[str | None], code: str, unit_conversion: float) -> int:
    """Remembers every non-empty name for this product. Returns how many names were saved."""
    saved = 0
    for name in names:
        if name and name.strip():
            save_alias(conn, name, code, unit_conversion)
            saved += 1
    return saved


def _line_conversion(conn: sqlite3.Connection, line: dict) -> float:
    conversion = line.get("unit_conversion") or 1.0
    if conversion == 1.0 and line.get("matched_code"):
        conversion = suggest_wholesale_conversion(conn, line["matched_code"], line.get("raw_unit_price"))
    return conversion


def learn_all_matched_lines(conn: sqlite3.Connection) -> int:
    """Backfill: remember every already-matched line of every invoice (e.g.
    the trial deliveries) WITHOUT touching any price or invoice line.
    Newest invoice wins when the same name was matched twice. Returns the
    number of matched lines learned."""
    rows = conn.execute(
        "SELECT id, raw_name, raw_name_ru, raw_unit_price, matched_code, unit_conversion "
        "FROM supplier_invoice_lines WHERE matched_code IS NOT NULL ORDER BY supplier_invoice_id, id"
    ).fetchall()
    for line_id, raw_name, raw_name_ru, price, code, conversion in rows:
        line = {"unit_conversion": conversion, "matched_code": code, "raw_unit_price": price}
        learn_alias(conn, [raw_name, raw_name_ru], code, _line_conversion(conn, line))
    return len(rows)


def find_known_match(conn: sqlite3.Connection, name_latin: str, name_ru: str, raw_unit_price: float | None = None) -> dict | None:
    """The product + conversion for a freshly AI-read row, or None when not sure:
    1) exact remembered name (Latin, then Russian), 2) the product's own
    catalog Russian name, 3) a clearly-closest remembered wording."""
    found = get_alias(conn, name_latin) if name_latin else None
    if found is None and name_ru:
        found = get_alias(conn, name_ru)
    if found is None and name_ru:
        row = conn.execute(
            "SELECT code FROM products WHERE name_ru != '' AND lower(name_ru) = lower(?)", (name_ru.strip(),)
        ).fetchone()
        if row:
            found = {"code": row[0], "unit_conversion": 1.0}
    if found is None:
        mine = [w for w in (_words(name_latin), _words(name_ru)) if w]
        best_by_code: dict[str, tuple[float, float]] = {}
        if mine:
            for key, code, conversion in conn.execute(
                "SELECT raw_name_normalized, product_code, unit_conversion FROM supplier_aliases"
            ):
                key_words = _words(key)
                if not key_words:
                    continue
                score = max(_soft_overlap(m, key_words) for m in mine)
                if score > best_by_code.get(code, (0.0, 1.0))[0]:
                    best_by_code[code] = (score, conversion)
        ranked = sorted(best_by_code.items(), key=lambda kv: -kv[1][0])
        if ranked and ranked[0][1][0] >= _FUZZY_MIN:
            runner_up = ranked[1][1][0] if len(ranked) > 1 else 0.0
            if ranked[0][1][0] - runner_up >= _FUZZY_MARGIN:
                found = {"code": ranked[0][0], "unit_conversion": ranked[0][1][1]}
    if found is None or get_product(conn, found["code"]) is None:
        return None
    conversion = found["unit_conversion"] or 1.0
    if conversion == 1.0:
        conversion = suggest_wholesale_conversion(conn, found["code"], raw_unit_price)
    return {"code": found["code"], "unit_conversion": conversion}


def below_cost_overrides(conn: sqlite3.Connection, codes) -> list[dict]:
    """Products among `codes` whose fixed wholesale-price exception is now BELOW
    cost x bulk size (a cost rise from a supplier invoice can silently turn it
    into a loss). Shown right after "Áp dụng giá mới", when the loss starts."""
    out = []
    for code in sorted(set(codes)):
        product = get_product(conn, code)
        if not product or not product["bulk_price_override"] or not product["bulk_qty"]:
            continue
        cost_total = product["cost_price"] * product["bulk_qty"]
        if product["bulk_price_override"] < cost_total:
            out.append({"code": code, "override": product["bulk_price_override"], "cost_total": cost_total})
    return out


# ---- Deleting a supplier invoice ----

_DELETED_KEYS_META = "deleted_photo_keys"


def _deleted_photo_keys(conn: sqlite3.Connection) -> set[str]:
    row = conn.execute("SELECT value FROM shop_meta WHERE key = ?", (_DELETED_KEYS_META,)).fetchone()
    return set(row[0].split("\n")) if row and row[0] else set()


def delete_supplier_invoice(conn: sqlite3.Connection, invoice_id: int) -> None:
    """Removes the invoice and its lines. Cost prices it already applied to the
    catalog stay as they are (price_history keeps the record) -- only the
    invoice itself goes. The photo/PDF file in data/supplier_invoices is NOT
    deleted (real data). A Telegram-synced invoice's key is remembered, so the
    next "Đồng bộ từ Telegram" does not bring the same photo back."""
    row = conn.execute("SELECT source_key FROM supplier_invoices WHERE id = ?", (invoice_id,)).fetchone()
    if row is None:
        raise ValueError(f"no such supplier invoice: {invoice_id}")
    source_key = row[0]
    if source_key:
        keys = _deleted_photo_keys(conn) | {source_key}
        conn.execute(
            "INSERT INTO shop_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_DELETED_KEYS_META, "\n".join(sorted(keys))),
        )
    # nothing may keep pointing at the deleted invoice (foreign keys are enforced)
    conn.execute("UPDATE invoices SET supplier_invoice_id = NULL WHERE supplier_invoice_id = ?", (invoice_id,))
    conn.execute("UPDATE order_batches SET supplier_invoice_id = NULL WHERE supplier_invoice_id = ?", (invoice_id,))
    conn.execute("DELETE FROM supplier_invoice_lines WHERE supplier_invoice_id = ?", (invoice_id,))
    conn.execute("DELETE FROM supplier_invoices WHERE id = ?", (invoice_id,))
    conn.commit()
