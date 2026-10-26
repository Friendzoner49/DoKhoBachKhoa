"""Orders placed through the Telegram bot, pulled in from Cloudflare
Workers (GET /sync/orders) -- see CLAUDE.md section 6/7 (lần 13). This
table is what the app actually acts on; the bot's own Telegram message
to the admin is just a (sometimes-failing) notification, not the real
record -- see bot/src/onlineOrdersSync.js.

Qt-free, like every other shop.core module -- shop.ui.online_orders_page
is where this gets a UI.
"""
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote

from shop.core import invoices as invoices_core
from shop.core.customers import get_customer
from shop.core.products import get_product


class SyncError(Exception):
    """A Vietnamese message safe to show directly in a QMessageBox --
    network/auth failures talking to the Worker, not a programming bug."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_SYNC_BACKOFF_MS = 10 * 60 * 1000  # see docstring below

_SYNC_FLOOR_META_KEY = "sync_floor_ms"
_LEGACY_SYNC_FLOOR_META_KEY = "sync_floor"  # format: "sync:<13-digit-ms>" -- see _sync_floor_ms


def set_sync_floor(conn: sqlite3.Connection, now_ms: int | None = None) -> None:
    """Called by shop.core.reset right after wiping online_orders (and
    supplier_invoices -- see shop.core.supplier_invoices), so the next
    sync doesn't immediately re-pull every pre-reset test record still
    sitting in the bot's KV (90-day TTL) -- a factory reset must
    actually stay reset. Stored as a bare millisecond timestamp (not
    prefixed) because it's shared by two different key namespaces --
    online_orders' "sync:..." keys AND supplier_invoices' "photo:..."
    keys -- which each build their own prefixed floor string from this
    same number via _sync_floor()/supplier_invoices._photo_sync_floor().
    Comparing a "photo:" key against a "sync:"-prefixed floor string (or
    vice versa) would sort wrong lexicographically and reject
    everything forever -- the two floors must never be compared across
    prefixes, only within the same one."""
    ts = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    conn.execute(
        "INSERT INTO shop_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_SYNC_FLOOR_META_KEY, str(ts)),
    )
    conn.commit()


def _sync_floor_ms(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM shop_meta WHERE key = ?", (_SYNC_FLOOR_META_KEY,)).fetchone()
    if row:
        return int(row[0])
    # Fallback for a floor written before this key was renamed (lần 20) --
    # a real reset run under the OLD format ("sync_floor" -> "sync:<ms>")
    # must keep protecting against pre-reset KV records re-appearing,
    # not silently stop working the moment this code changed under it.
    legacy = conn.execute(
        "SELECT value FROM shop_meta WHERE key = ?", (_LEGACY_SYNC_FLOOR_META_KEY,)
    ).fetchone()
    if legacy and legacy[0].startswith("sync:"):
        try:
            return int(legacy[0].split(":", 1)[1])
        except ValueError:
            return None
    return None


def _sync_floor(conn: sqlite3.Connection) -> str | None:
    ms = _sync_floor_ms(conn)
    return f"sync:{ms:013d}" if ms is not None else None


def _last_source_key(conn: sqlite3.Connection) -> str | None:
    # The bot's sync: keys are time-sortable strings (see
    # onlineOrdersSync.js), so the largest one we already have is a
    # natural "since" cursor for the next pull -- EXCEPT Cloudflare KV's
    # list() is only eventually consistent (propagation across edge
    # locations can lag up to roughly a minute), and the order's
    # original write (near Telegram's webhook) and this app's sync call
    # (from Russia) can hit different edge locations. A strict
    # "strictly newer than the last key I've seen" cursor could then
    # permanently skip an order that was still propagating at sync
    # time. Back the cursor off by 10 minutes of margin instead --
    # source_key is UNIQUE, so re-seeing an already-synced order inside
    # that window is silently skipped (see _insert_online_order), never
    # duplicated.
    max_key = conn.execute("SELECT MAX(source_key) FROM online_orders").fetchone()[0]
    backed_off = None
    if max_key:
        try:
            prefix, rest = max_key.split(":", 1)
            ts = int(rest.split("-", 1)[0]) - _SYNC_BACKOFF_MS
            backed_off = f"{prefix}:{max(ts, 0):013d}"
        except (ValueError, IndexError):
            backed_off = max_key

    floor = _sync_floor(conn)
    if floor and backed_off:
        return max(floor, backed_off)
    return floor or backed_off


def sync_from_bot(conn: sqlite3.Connection, worker_url: str, sync_secret: str, timeout: float = 10.0) -> int:
    """Pulls new orders and inserts them (source_key is UNIQUE, so a
    re-pulled order is silently skipped, not duplicated). Returns how
    many were newly inserted. Never writes to products/pricing -- only
    convert_to_invoice() does that, from CURRENT prices, not whatever
    the bot estimated at order time."""
    if not worker_url or not sync_secret:
        raise SyncError("Chưa cài đặt đồng bộ: cần nhập Worker URL và Mã đồng bộ trước (xem bot/README.md).")

    since = _last_source_key(conn)
    url = worker_url.rstrip("/") + "/sync/orders"
    if since:
        url += f"?since={quote(since)}"

    # The User-Agent matters: Cloudflare's edge-level bot protection
    # blocks Python's default "Python-urllib/..." signature with its
    # own 403 (body "error code: 1010"), BEFORE the request ever reaches
    # our Worker code -- confirmed live (curl with the same secret got
    # 200, urllib without this header got blocked at the edge). A
    # correct SYNC_SECRET is not enough without this.
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
        # A 200 response that isn't valid JSON. This endpoint has been
        # live since lần 13, so unlike its sibling in
        # supplier_invoices.sync_photos_from_bot (a genuinely newer
        # endpoint that might not be deployed yet), the realistic cause
        # here is a VPN/captive-portal page intercepting the response,
        # not a missing route. json.loads() raising must not escape as
        # a bare exception into the Qt slot calling this either way.
        raise SyncError(
            "Không đọc được phản hồi từ bot (không phải JSON) -- có thể do VPN hoặc mạng đang chặn/chuyển hướng. "
            "Kiểm tra lại mạng rồi thử lại."
        ) from e

    inserted = 0
    for order in data.get("orders", []):
        if _insert_online_order(conn, order):
            inserted += 1
    return inserted


def _insert_online_order(conn: sqlite3.Connection, order: dict) -> bool:
    floor = _sync_floor(conn)
    if floor and order["key"] <= floor:
        # Pre-reset order the Worker returned anyway (its own `since`
        # filter is the first line of defense, this is the second --
        # see set_sync_floor's docstring). Not an error, just skipped.
        return False
    try:
        cur = conn.execute(
            """
            INSERT INTO online_orders
                (source_key, telegram_chat_id, customer_label, customer_phone, total_estimated, placed_at, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["key"],
                str(order["telegram_chat_id"]),
                order.get("customer_label") or "",
                order.get("customer_phone"),
                int(order.get("total_estimated") or 0),
                order.get("created_at") or _now(),
                _now(),
            ),
        )
    except sqlite3.IntegrityError:
        return False  # already synced before -- source_key is UNIQUE
    online_order_id = cur.lastrowid
    for line in order.get("lines", []):
        conn.execute(
            "INSERT INTO online_order_lines (online_order_id, code, qty, name_at_order, price_at_order) VALUES (?, ?, ?, ?, ?)",
            (online_order_id, line["code"], line["qty"], line.get("name") or line["code"], int(line.get("price") or 0)),
        )
    conn.commit()
    return True


def list_online_orders(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    sql = (
        "SELECT id, telegram_chat_id, customer_label, customer_phone, total_estimated, "
        "status, linked_invoice_id, placed_at, batch_id, arrival_notified_at FROM online_orders"
    )
    params: list = []
    if status is not None:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY placed_at DESC"
    cols = ["id", "telegram_chat_id", "customer_label", "customer_phone", "total_estimated", "status", "linked_invoice_id", "placed_at", "batch_id", "arrival_notified_at"]
    orders = [dict(zip(cols, row)) for row in conn.execute(sql, params)]
    for o in orders:
        o["lines"] = get_online_order_lines(conn, o["id"])
    return orders


def get_online_order_lines(conn: sqlite3.Connection, online_order_id: int) -> list[dict]:
    cols = ["id", "code", "qty", "name_at_order", "price_at_order", "excluded", "original_qty"]
    rows = conn.execute(
        f"SELECT {', '.join(cols)} FROM online_order_lines WHERE online_order_id = ? ORDER BY id",
        (online_order_id,),
    ).fetchall()
    lines = [dict(zip(cols, row)) for row in rows]
    for line in lines:
        line["excluded"] = bool(line["excluded"])
    return lines


def pending_demand_by_code(conn: sqlite3.Connection) -> list[dict]:
    """Total quantity on orders NOT YET in any batch -- what's piling up
    since the last "Chốt đợt hàng mới" (request #2, lần 19), shown by
    the "Cần nhập hàng gì?" button as a preview of the next batch.
    Deliberately NOT the list to actually order from the supplier --
    that's batch_demand_by_code() for a CLOSED batch, reviewed and
    pruned of unavailable items via "Duyệt đợt hàng…". Summing every
    still-'cho_xu_ly' order here regardless of batch would silently mix
    an already-reviewed batch's confirmed-available demand with brand
    new, not-yet-reviewed orders -- two different things that must
    never be added together into one number an owner might place a
    real supplier order from."""
    rows = conn.execute(
        """
        SELECT ool.code, SUM(ool.qty) AS total_qty, MAX(ool.name_at_order) AS name
        FROM online_order_lines ool
        JOIN online_orders oo ON oo.id = ool.online_order_id
        WHERE oo.status = 'cho_xu_ly' AND oo.batch_id IS NULL AND ool.excluded = 0
        GROUP BY ool.code
        ORDER BY total_qty DESC
        """
    ).fetchall()
    return [{"code": r[0], "total_qty": r[1], "name": r[2]} for r in rows]


def close_batch(conn: sqlite3.Connection) -> int:
    """"Chốt đợt hàng mới" (lần 19, request #2): snapshots every order
    still 'cho_xu_ly' and not yet in a batch into a brand new one. The
    caller should sync_from_bot() first so anything the customer placed
    before clicking "chốt" but not yet pulled in gets a chance to land
    in THIS batch -- an order that only shows up after this call (even
    if placed earlier, e.g. Cloudflare KV propagation lag) simply stays
    unbatched and waits for the next close. That's a documented, tested
    edge case (see tests/test_online_orders.py), not a bug: the window
    is small and the owner already runs "Đồng bộ ngay" right before."""
    now = _now()
    cur = conn.execute("INSERT INTO order_batches (closed_at) VALUES (?)", (now,))
    batch_id = cur.lastrowid
    conn.execute(
        "UPDATE online_orders SET batch_id = ? WHERE status = 'cho_xu_ly' AND batch_id IS NULL",
        (batch_id,),
    )
    conn.commit()
    return batch_id


def list_batches(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, closed_at FROM order_batches ORDER BY id DESC").fetchall()
    return [{"id": r[0], "closed_at": r[1]} for r in rows]


def order_batch_label(batch_id: int | None) -> str:
    return f"Đợt #{batch_id}" if batch_id is not None else "Chưa chốt đợt"


def batch_demand_by_code(conn: sqlite3.Connection, batch_id: int) -> list[dict]:
    """Same shape as pending_demand_by_code, scoped to one batch -- what
    the owner reviews in "Duyệt đợt hàng…" before deciding what the
    supplier can't fulfil this round."""
    rows = conn.execute(
        """
        SELECT ool.code, SUM(ool.qty) AS total_qty, MAX(ool.name_at_order) AS name, COUNT(DISTINCT oo.id) AS order_count
        FROM online_order_lines ool
        JOIN online_orders oo ON oo.id = ool.online_order_id
        WHERE oo.batch_id = ? AND oo.status = 'cho_xu_ly' AND ool.excluded = 0
        GROUP BY ool.code
        ORDER BY name
        """,
        (batch_id,),
    ).fetchall()
    return [{"code": r[0], "total_qty": r[1], "name": r[2], "order_count": r[3]} for r in rows]


def batch_excluded_codes(conn: sqlite3.Connection, batch_id: int) -> list[dict]:
    """Codes already struck from this batch (see set_code_excluded), so
    the review dialog can offer "Khôi phục" without the owner having to
    retype a code by hand."""
    rows = conn.execute(
        """
        SELECT ool.code, MAX(ool.name_at_order) AS name, COUNT(DISTINCT oo.id) AS order_count
        FROM online_order_lines ool
        JOIN online_orders oo ON oo.id = ool.online_order_id
        WHERE oo.batch_id = ? AND oo.status = 'cho_xu_ly' AND ool.excluded = 1
        GROUP BY ool.code
        ORDER BY name
        """,
        (batch_id,),
    ).fetchall()
    return [{"code": r[0], "name": r[1], "order_count": r[2]} for r in rows]


def _recompute_order_total(conn: sqlite3.Connection, online_order_id: int) -> None:
    total = conn.execute(
        "SELECT COALESCE(SUM(qty * price_at_order), 0) FROM online_order_lines WHERE online_order_id = ? AND excluded = 0",
        (online_order_id,),
    ).fetchone()[0]
    conn.execute("UPDATE online_orders SET total_estimated = ? WHERE id = ?", (round(total), online_order_id))


def set_code_excluded(conn: sqlite3.Connection, batch_id: int, code: str, excluded: bool) -> list[int]:
    """The owner confirms the supplier doesn't have `code` this round
    (request #1) -- or undoes that. Strikes/restores it on every still-
    pending order in the batch at once (one click instead of hunting
    through orders one by one), recomputing each order's estimated
    total. Soft-exclude (see migration 007), never DELETE: the line
    stays, just flagged, so it's both visible for telling the affected
    customer and reversible on a misclick. convert_to_invoice() skips
    excluded lines. Returns the ids of affected orders."""
    rows = conn.execute(
        "SELECT DISTINCT oo.id FROM online_order_lines ool JOIN online_orders oo ON oo.id = ool.online_order_id "
        "WHERE oo.batch_id = ? AND oo.status = 'cho_xu_ly' AND ool.code = ?",
        (batch_id, code),
    ).fetchall()
    affected = [r[0] for r in rows]
    conn.execute(
        "UPDATE online_order_lines SET excluded = ? WHERE code = ? AND online_order_id IN "
        "(SELECT id FROM online_orders WHERE batch_id = ? AND status = 'cho_xu_ly')",
        (int(excluded), code, batch_id),
    )
    for oid in affected:
        _recompute_order_total(conn, oid)
    conn.commit()
    return affected


def link_invoice_to_batch(conn: sqlite3.Connection, supplier_invoice_id: int, batch_id: int) -> None:
    """"Nối với hóa đơn NCC" (25/10/2026): records that this delivery
    (supplier invoice) fulfils this batch of customer orders. The link
    lives on supplier_invoices, not order_batches -- a single delivery
    can arrive as SEVERAL /hangve photos (bot/README.md mục 13 tells
    the owner to send one per message), each its own supplier_invoices
    row, so a batch needs to accept many invoices, not just one."""
    if conn.execute("SELECT 1 FROM order_batches WHERE id = ?", (batch_id,)).fetchone() is None:
        raise ValueError(f"Unknown batch id: {batch_id}")
    if conn.execute("SELECT 1 FROM supplier_invoices WHERE id = ?", (supplier_invoice_id,)).fetchone() is None:
        raise ValueError(f"Unknown supplier invoice id: {supplier_invoice_id}")
    conn.execute(
        "UPDATE supplier_invoices SET order_batch_id = ? WHERE id = ?", (batch_id, supplier_invoice_id)
    )
    conn.commit()


def unlink_invoice_from_batch(conn: sqlite3.Connection, supplier_invoice_id: int) -> None:
    conn.execute("UPDATE supplier_invoices SET order_batch_id = NULL WHERE id = ?", (supplier_invoice_id,))
    conn.commit()


def batch_linked_invoices(conn: sqlite3.Connection, batch_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, invoice_number, invoice_date, applied_at FROM supplier_invoices WHERE order_batch_id = ? ORDER BY id",
        (batch_id,),
    ).fetchall()
    return [{"id": r[0], "invoice_number": r[1], "invoice_date": r[2], "applied_at": r[3]} for r in rows]


def batch_delivered_by_code(conn: sqlite3.Connection, batch_id: int) -> tuple[dict[str, float], int]:
    """Quantity actually delivered per product code, summed across EVERY
    supplier invoice linked to this batch (raw_qty * unit_conversion,
    same normalization as line_cost_preview). Also returns the count of
    lines in those invoices still missing a matched_code or a raw_qty --
    the caller must treat the delivered numbers as unreliable and warn
    the owner before relying on them, because an unmatched line makes
    whatever product it actually was look like 0 delivered (100% short)
    when it may well have arrived (see advisor review, 25/10/2026)."""
    rows = conn.execute(
        """
        SELECT sil.matched_code, SUM(sil.raw_qty * sil.unit_conversion)
        FROM supplier_invoice_lines sil
        JOIN supplier_invoices si ON si.id = sil.supplier_invoice_id
        WHERE si.order_batch_id = ? AND sil.matched_code IS NOT NULL AND sil.raw_qty IS NOT NULL
        GROUP BY sil.matched_code
        """,
        (batch_id,),
    ).fetchall()
    delivered = {code: qty for code, qty in rows}
    incomplete = conn.execute(
        """
        SELECT COUNT(*)
        FROM supplier_invoice_lines sil
        JOIN supplier_invoices si ON si.id = sil.supplier_invoice_id
        WHERE si.order_batch_id = ? AND (sil.matched_code IS NULL OR sil.raw_qty IS NULL)
        """,
        (batch_id,),
    ).fetchone()[0]
    return delivered, incomplete


def batch_shortage_report(conn: sqlite3.Connection, batch_id: int) -> list[dict]:
    """For every code still demanded in this batch (batch_demand_by_code,
    already excludes batch-wide-struck codes), compares ordered vs.
    delivered quantity. diff > 0 is a shortage (less arrived than every
    customer together ordered), diff < 0 is a surplus -- either way the
    owner may want to adjust specific customers' lines by hand (request
    25/10/2026: "tôi sẽ cần tinh chỉnh lại các đơn của khách... thiếu
    hay thừa"), not an automatic reallocation. Only codes where
    diff != 0 are returned; an exact match needs no attention."""
    delivered, _incomplete = batch_delivered_by_code(conn, batch_id)
    report = []
    for row in batch_demand_by_code(conn, batch_id):
        got = delivered.get(row["code"], 0.0)
        diff = row["total_qty"] - got
        if abs(diff) > 1e-9:
            report.append({"code": row["code"], "name": row["name"], "ordered": row["total_qty"], "delivered": got, "diff": diff})
    return report


def list_batch_order_lines_for_code(conn: sqlite3.Connection, batch_id: int, code: str) -> list[dict]:
    """Every still-pending customer order line for `code` in this batch,
    for the owner to adjust one at a time (set_order_line_qty /
    set_order_line_excluded) when batch_shortage_report flags it --
    finer-grained than set_code_excluded, which always strikes a code
    for the WHOLE batch at once."""
    rows = conn.execute(
        """
        SELECT ool.id, oo.id, oo.customer_label, ool.qty, ool.excluded, ool.original_qty
        FROM online_order_lines ool
        JOIN online_orders oo ON oo.id = ool.online_order_id
        WHERE oo.batch_id = ? AND oo.status = 'cho_xu_ly' AND ool.code = ?
        ORDER BY oo.id
        """,
        (batch_id, code),
    ).fetchall()
    return [
        {
            "line_id": r[0],
            "online_order_id": r[1],
            "customer_label": r[2],
            "qty": r[3],
            "excluded": bool(r[4]),
            "original_qty": r[5],
        }
        for r in rows
    ]


def set_order_line_qty(conn: sqlite3.Connection, line_id: int, new_qty: float) -> None:
    """Adjusts ONE customer's line (not the whole batch/code) -- for the
    shortage-reconciliation screen, where one customer might get less
    and another more of the same scarce item. Recomputes the parent
    order's total_estimated the same way set_code_excluded does.

    original_qty is stamped on the FIRST edit only (left alone on later
    edits, e.g. the owner correcting their own adjustment twice) -- it's
    what the customer actually asked for, so the arrival DM can say
    "chỉ giao 3/5" instead of reporting the adjusted number as if it
    were the original request."""
    if new_qty <= 0:
        raise ValueError("Số lượng phải lớn hơn 0 -- dùng \"loại khỏi đơn\" nếu khách không nhận món này.")
    row = conn.execute(
        "SELECT online_order_id, qty, original_qty FROM online_order_lines WHERE id = ?", (line_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown order line id: {line_id}")
    online_order_id, current_qty, original_qty = row
    if original_qty is None:
        conn.execute("UPDATE online_order_lines SET qty = ?, original_qty = ? WHERE id = ?", (new_qty, current_qty, line_id))
    else:
        conn.execute("UPDATE online_order_lines SET qty = ? WHERE id = ?", (new_qty, line_id))
    _recompute_order_total(conn, online_order_id)
    conn.commit()


def set_order_line_excluded(conn: sqlite3.Connection, line_id: int, excluded: bool) -> None:
    """Same idea as set_code_excluded but for exactly ONE customer's
    line, not every order in the batch -- e.g. the supplier had enough
    for everyone except this one customer's extra-large order."""
    online_order_id = conn.execute(
        "SELECT online_order_id FROM online_order_lines WHERE id = ?", (line_id,)
    ).fetchone()
    if online_order_id is None:
        raise ValueError(f"Unknown order line id: {line_id}")
    conn.execute("UPDATE online_order_lines SET excluded = ? WHERE id = ?", (int(excluded), line_id))
    _recompute_order_total(conn, online_order_id[0])
    conn.commit()


def mark_cancelled(conn: sqlite3.Connection, online_order_id: int) -> None:
    conn.execute(
        "UPDATE online_orders SET status = 'da_huy' WHERE id = ? AND status = 'cho_xu_ly'", (online_order_id,)
    )
    conn.commit()


def linked_customer_id(conn: sqlite3.Connection, telegram_chat_id: str) -> int | None:
    row = conn.execute(
        "SELECT customer_id FROM telegram_customer_links WHERE telegram_chat_id = ?", (str(telegram_chat_id),)
    ).fetchone()
    return row[0] if row else None


def link_customer(conn: sqlite3.Connection, telegram_chat_id: str, customer_id: int) -> None:
    conn.execute(
        """
        INSERT INTO telegram_customer_links (telegram_chat_id, customer_id) VALUES (?, ?)
        ON CONFLICT(telegram_chat_id) DO UPDATE SET customer_id = excluded.customer_id
        """,
        (str(telegram_chat_id), customer_id),
    )
    conn.commit()


def convert_to_invoice(conn: sqlite3.Connection, online_order_id: int, customer_id: int) -> tuple[int, list[str], list[str]]:
    """Creates a draft invoice for customer_id, one line per order line,
    priced from CURRENT cost_price/markup via invoices.add_line -- never
    trusts the bot's price_at_order snapshot. A code no longer in the
    catalog is skipped and reported back in `dropped`, same spirit as
    the bot's own dropped-codes handling. A line the owner already
    struck during "Duyệt đợt hàng…" (set_code_excluded, request #1) is
    skipped and reported in `excluded` instead -- the customer is never
    billed for something the supplier didn't have. Marks the online
    order da_tao_hoa_don, links it to the new invoice, and remembers
    this Telegram chat -> customer mapping for next time. Returns
    (invoice_id, dropped_codes, excluded_codes)."""
    row = conn.execute("SELECT telegram_chat_id, status FROM online_orders WHERE id = ?", (online_order_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown online order id: {online_order_id}")
    telegram_chat_id, status = row
    if status != "cho_xu_ly":
        raise ValueError("Đơn này đã được xử lý hoặc đã hủy rồi.")

    customer = get_customer(conn, customer_id)
    if customer is None:
        raise ValueError(f"Unknown customer id: {customer_id}")

    lines = get_online_order_lines(conn, online_order_id)
    dropped: list[str] = []
    excluded: list[str] = []
    convertible: list[dict] = []
    for line in lines:
        if line["excluded"]:
            excluded.append(line["code"])
        elif get_product(conn, line["code"]) is None:
            dropped.append(line["code"])
        else:
            convertible.append(line)

    if not convertible:
        # Every line was excluded (request #1) and/or dropped -- an
        # invoice with 0 lines would be a draft that online_orders.
        # linked_invoice_id then points AT, and invoices.delete_draft_invoice
        # would hit a FOREIGN KEY failure trying to remove it (nothing
        # upstream nulls that reference first). Nothing left to bill, so
        # don't create one at all -- the caller (convert_selected) should
        # point the owner at "Hủy đơn" instead.
        raise ValueError(
            "Mọi mặt hàng trong đơn này đã bị loại hoặc không còn trong danh mục -- "
            "không có gì để lên hóa đơn. Dùng \"Hủy đơn\" thay vì tạo hóa đơn."
        )

    invoice_id = invoices_core.create_invoice(conn, customer_id)
    for line in convertible:
        # Same markup the customer gets on every other invoice -- never
        # falls back to the public default here, same as invoice_editor.py.
        invoices_core.add_line(conn, invoice_id, line["code"], line["qty"], markup_pct=customer["default_markup_pct"])

    conn.execute(
        "UPDATE online_orders SET status = 'da_tao_hoa_don', linked_invoice_id = ? WHERE id = ?",
        (invoice_id, online_order_id),
    )
    conn.commit()
    link_customer(conn, telegram_chat_id, customer_id)
    return invoice_id, dropped, excluded
