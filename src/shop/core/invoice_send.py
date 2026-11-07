"""Send a finalized customer invoice to that customer on Telegram, as a plain
text summary (no file). Goes through the same Worker route and credential as
"hàng đã về" (POST /notify/arrival: it only relays {chat_id, text} pairs).

Privacy (CLAUDE.md section 6): only THIS customer's own invoice, only to the
Telegram chat(s) linked to THIS customer (telegram_customer_links, created
when an online order from that chat was turned into an invoice).
"""
import json
import sqlite3
import urllib.error
from datetime import datetime, timezone

from shop.core.customers import get_customer
from shop.core.invoices import get_invoice
from shop.core.summary import customer_debt
from shop.core.supplier_invoices import _worker_request
from shop.paths import payment_info


class InvoiceSendError(Exception):
    """Vietnamese message safe to show directly in a QMessageBox."""


def _money(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _qty(n: float) -> str:
    return f"{n:g}"


def customer_chat_ids(conn: sqlite3.Connection, customer_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT telegram_chat_id FROM telegram_customer_links WHERE customer_id = ? ORDER BY telegram_chat_id",
        (customer_id,),
    ).fetchall()
    return [r[0] for r in rows]


def build_invoice_message(conn: sqlite3.Connection, invoice_id: int) -> str:
    invoice = get_invoice(conn, invoice_id)
    if invoice is None:
        raise InvoiceSendError("Không tìm thấy hóa đơn này.")
    try:
        day = datetime.fromisoformat(invoice["invoice_date"]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        day = invoice["invoice_date"] or ""
    parts = [f"🧾 Hóa đơn #{invoice['id']} — {day}", ""]
    for line in invoice["lines"]:
        name = line["product_name_snapshot"]
        if line["line_total"] < 0:  # discount line
            parts.append(f"• {name}: −{_money(-line['line_total'])} ₽")
        elif line["qty"] == 1 and not line["product_code"]:  # custom fee line
            parts.append(f"• {name}: {_money(line['line_total'])} ₽")
        else:
            parts.append(f"• {name}: {_qty(line['qty'])} × {_money(line['unit_price'])} = {_money(line['line_total'])} ₽")
    parts += ["", f"Tổng: {_money(invoice['total'])} ₽"]
    parts.append(f"Công nợ hiện tại: {_money(customer_debt(conn, invoice['customer_id']))} ₽")
    transfer_lines = [line.strip() for line in payment_info().splitlines() if line.strip()]
    if transfer_lines:  # where to pay -- near the end, just before the thanks
        parts += ["", "💳 Chuyển khoản:", *transfer_lines]
    parts += ["", "Xin cảm ơn quý khách!"]
    return "\n".join(parts)


def send_invoice_to_customer(conn: sqlite3.Connection, invoice_id: int, worker_url: str, sync_secret: str) -> int:
    """Returns how many chats the Worker confirmed. Marks telegram_sent_at only
    on confirmation, so a failed send can simply be retried."""
    if not worker_url or not sync_secret:
        raise InvoiceSendError(
            'Chưa cài đặt đồng bộ: cần nhập Worker URL và Mã đồng bộ trước (tab "Đơn hàng online" → "Cài đặt đồng bộ…").'
        )
    invoice = get_invoice(conn, invoice_id)
    if invoice is None:
        raise InvoiceSendError("Không tìm thấy hóa đơn này.")
    if invoice["status"] != "finalized":
        raise InvoiceSendError("Chỉ gửi được hóa đơn ĐÃ HOÀN TẤT (hóa đơn nháp còn có thể đổi giá).")
    customer = get_customer(conn, invoice["customer_id"])
    chats = customer_chat_ids(conn, invoice["customer_id"])
    if not chats:
        raise InvoiceSendError(
            f"Khách \"{customer['name']}\" chưa liên kết Telegram. Liên kết tự có khi bạn tạo hóa đơn từ đơn online "
            "của khách đó (tab Đơn hàng online)."
        )
    text = build_invoice_message(conn, invoice_id)
    try:
        raw = _worker_request(
            worker_url, sync_secret, "/notify/arrival",
            {"messages": [{"chat_id": chat, "text": text} for chat in chats]}, timeout=30.0,
        )
        data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise InvoiceSendError("Mã đồng bộ không đúng. Kiểm tra lại Mã đồng bộ trong app và SYNC_SECRET trên Cloudflare.") from e
        raise InvoiceSendError(f"Bot trả về lỗi (HTTP {e.code}). Thử lại sau.") from e
    except urllib.error.URLError as e:
        raise InvoiceSendError("Không kết nối được tới bot. Kiểm tra mạng (có thể cần VPN nếu đang ở Nga) rồi thử lại.") from e
    except (TimeoutError, OSError) as e:
        raise InvoiceSendError("Kết nối tới bot quá lâu -- có thể tin đã gửi. Hỏi lại khách trước khi gửi lần nữa.") from e
    except ValueError as e:
        raise InvoiceSendError("Bot chưa hỗ trợ gửi tin -- cần deploy lại Worker (xem bot/README.md).") from e
    if not isinstance(data, dict) or "results" not in data:
        raise InvoiceSendError("Bot chưa hỗ trợ gửi tin -- cần deploy lại Worker (xem bot/README.md).")
    ok = [r for r in data["results"] if r.get("ok")]
    if not ok:
        reason = next((r.get("error") for r in data["results"] if r.get("error")), "không rõ lý do")
        raise InvoiceSendError(f"Không gửi được cho khách \"{customer['name']}\": {reason}")
    conn.execute(
        "UPDATE invoices SET telegram_sent_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), invoice_id),
    )
    conn.commit()
    return len(ok)
