"""Sends each customer in a closed order batch a private "hàng đã về"
DM once the owner links the batch to the supplier invoice(s) that
fulfil it -- request 25/10/2026 (the other half of lần 18's "hàng về
-> thu tiền" plan; "📢 Đăng lên kênh" from lần 21 already covers the
public channel side).

Goes through the SAME Worker + credential as every other app<->bot
call (shop.paths.bot_sync_settings, SYNC_SECRET) -- one "app talks to
Worker" credential, not a secret per endpoint (CLAUDE.md section 2).

No money total in the DM: a line's price is only fixed later, at
convert_to_invoice() time, with that customer's own markup -- a total
shown here could disagree with the real invoice. Each customer sees
ONLY their own lines (CLAUDE.md section 6's privacy rule): the Worker
call sends one message per chat_id, never a broadcast.
"""
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone

from shop.core.online_orders import get_online_order_lines, list_online_orders

_CHUNK_SIZE = 40  # Cloudflare Workers free tier: 50 subrequests per invocation (CLAUDE.md lần 13) -- leave margin


class NotifyError(Exception):
    """Vietnamese message safe to show directly in a QMessageBox."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fmt_qty(n: float) -> str:
    return f"{n:g}"


def build_customer_message(lines: list[dict]) -> str:
    """Pure function (no DB/network) so it's easy to test and to review
    by eye. `lines` is get_online_order_lines()'s own shape -- only this
    one customer's lines, never another customer's."""
    delivered = [l for l in lines if not l["excluded"]]
    missing = [l for l in lines if l["excluded"]]

    if not delivered:
        msg = "😔 Rất tiếc, đợt hàng này không có mặt hàng nào bạn đã đặt. Xin lỗi vì sự bất tiện, mong bạn thông cảm."
        if missing:
            msg += "\n\nMặt hàng không có đợt này:\n" + "\n".join(f"❌ {l['name_at_order']}" for l in missing)
        return msg

    parts = ["🎉 Hàng bạn đặt đã về, có thể tới nhận:\n"]
    for l in delivered:
        if l["original_qty"] is not None and l["original_qty"] != l["qty"]:
            parts.append(f"• {l['name_at_order']}: {_fmt_qty(l['qty'])} (đặt {_fmt_qty(l['original_qty'])})")
        else:
            parts.append(f"• {l['name_at_order']}: {_fmt_qty(l['qty'])}")
    for l in missing:
        parts.append(f"❌ {l['name_at_order']}: đợt này không có")
    return "\n".join(parts)


def prepare_arrival_messages(conn: sqlite3.Connection, batch_id: int) -> list[dict]:
    """One entry per customer order in this batch still awaiting
    notification (status cho_xu_ly, arrival_notified_at IS NULL) --
    already-converted or already-notified orders are skipped, so
    calling this (or send_arrival_notifications) again after a partial
    failure only retries what's left."""
    rows = conn.execute(
        "SELECT id, telegram_chat_id, customer_label FROM online_orders "
        "WHERE batch_id = ? AND status = 'cho_xu_ly' AND arrival_notified_at IS NULL ORDER BY id",
        (batch_id,),
    ).fetchall()
    out = []
    for order_id, chat_id, label in rows:
        lines = get_online_order_lines(conn, order_id)
        out.append(
            {
                "online_order_id": order_id,
                "telegram_chat_id": chat_id,
                "customer_label": label,
                "text": build_customer_message(lines),
            }
        )
    return out


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def send_arrival_notifications(conn: sqlite3.Connection, batch_id: int, worker_url: str, sync_secret: str, timeout: float = 30.0) -> dict:
    """Sends every pending "hàng đã về" DM for this batch. Marks
    arrival_notified_at ONLY for chat_ids the Worker explicitly confirms
    -- an undeployed Worker's catch-all route answers any unknown path
    with 200 "OK" (plain text, see lần 20), which must NOT be read as
    "every DM sent", or a later retry would never happen for customers
    who were never actually messaged. Returns
    {"sent": [...], "failed": [...]} -- failed entries (e.g. the
    customer blocked the bot, HTTP 403 from Telegram) are for the owner
    to contact by hand, see bot/README.md."""
    if not worker_url or not sync_secret:
        raise NotifyError(
            "Chưa cài đặt đồng bộ: cần nhập Worker URL và Mã đồng bộ trước "
            '(tab "Đơn hàng online" → "Cài đặt đồng bộ…").'
        )

    messages = prepare_arrival_messages(conn, batch_id)
    if not messages:
        return {"sent": [], "failed": []}

    url = worker_url.rstrip("/") + "/notify/arrival"
    sent: list[dict] = []
    failed: list[dict] = []
    for chunk in _chunks(messages, _CHUNK_SIZE):
        body = json.dumps(
            {"messages": [{"chat_id": m["telegram_chat_id"], "text": m["text"]} for m in chunk]}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "X-Sync-Secret": sync_secret,
                "User-Agent": "ShopApp-ArrivalNotify/1.0",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise NotifyError(
                    "Mã đồng bộ không đúng. Kiểm tra lại Mã đồng bộ trong app và SYNC_SECRET trên Cloudflare."
                ) from e
            raise NotifyError(f"Bot trả về lỗi (HTTP {e.code}). Thử lại sau.") from e
        except urllib.error.URLError as e:
            raise NotifyError(
                "Không kết nối được tới bot. Kiểm tra mạng (có thể cần VPN nếu đang ở Nga) rồi thử lại."
            ) from e
        except (TimeoutError, OSError) as e:
            raise NotifyError(
                "Kết nối tới bot quá lâu -- CÓ THỂ MỘT SỐ TIN ĐÃ GỬI dù máy chưa kịp nhận phản hồi. "
                "Bấm lại sẽ chỉ gửi cho khách CHƯA được đánh dấu đã báo, không gửi trùng."
            ) from e
        except ValueError as e:
            raise NotifyError("Bot chưa hỗ trợ gửi thông báo -- cần deploy lại Worker (xem bot/README.md).") from e

        if not isinstance(data, dict) or "results" not in data:
            raise NotifyError("Bot chưa hỗ trợ gửi thông báo -- cần deploy lại Worker (xem bot/README.md).")

        results_by_chat = {r["chat_id"]: r for r in data["results"]}
        for m in chunk:
            result = results_by_chat.get(m["telegram_chat_id"])
            if result is not None and result.get("ok"):
                conn.execute(
                    "UPDATE online_orders SET arrival_notified_at = ? WHERE id = ?", (_now(), m["online_order_id"])
                )
                sent.append(m)
            else:
                error = result.get("error") if result else "Không có phản hồi từ bot cho khách này."
                failed.append({**m, "error": error})
        conn.commit()

    return {"sent": sent, "failed": failed}
