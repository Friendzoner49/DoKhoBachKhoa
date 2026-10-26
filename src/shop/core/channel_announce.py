"""Post a seasonal-product announcement to the public Telegram channel
("Đồ khô Bách Khoa") -- lần 21 request: items on sale for only 3-5 days
need a push, not just a quiet appearance on the website. Goes through
the SAME Worker + credential as online-order/photo sync
(shop.paths.bot_sync_settings, SYNC_SECRET) -- one "app talks to
Worker" credential, not a secret per endpoint (CLAUDE.md section 2).

The image travels as base64 bytes, NOT a public URL: the natural click
order is "Cập nhật website giá" then "Đăng lên kênh", and GitHub Pages
can take anywhere from ~30s to a few minutes to actually serve a
freshly-pushed file -- a URL-based sendPhoto right after publishing
would race that deploy and fail. Uploading the local file directly
(same direction as /hangve's download, reversed) has no such race, and
no stale-cache risk if the photo gets swapped later.
"""
import base64
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone

from shop.core.pricing import PUBLIC_MARKUP_PCT, unit_price
from shop.core.products import get_product, set_channel_announced

# Same value as bot/wrangler.toml's SITE_BASE_URL and
# src/shop/tools/publish_site's target repo -- duplicated across
# Python/JS/docs already (see wrangler.toml's own comment), not worth
# a shared config file for a URL that's changed exactly once ever.
# Only used in the caption text here (the image itself is uploaded as
# bytes, not linked).
SITE_BASE_URL = "https://friendzoner49.github.io/DoKhoBachKhoa/"


class AnnounceError(Exception):
    """Vietnamese message safe to show directly in a QMessageBox."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _format_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def build_caption(product: dict) -> str:
    price = unit_price(product["cost_price"], PUBLIC_MARKUP_PCT)
    lines = [
        f"🆕 {product['name']}",
        f"{price:,.0f} RUB".replace(",", "."),
    ]
    if product.get("sale_until"):
        lines.append(f"⏳ Chỉ bán đến hết ngày {_format_date(product['sale_until'])}")
    lines.append("")
    lines.append(f"🛒 Đặt hàng: {SITE_BASE_URL}")
    return "\n".join(lines)


def announce_product(
    conn: sqlite3.Connection,
    code: str,
    worker_url: str,
    sync_secret: str,
    images_dir,
    timeout: float = 60.0,
) -> None:
    """Builds the caption from the product's CURRENT price/sale_until
    and asks the Worker to post it (with the image) to the channel.
    Marks channel_announced_at on success -- purely informational, the
    button stays usable for a re-post (e.g. closer to the sale window
    ending) regardless.

    timeout defaults much higher than the other sync_from_bot() calls
    in this project (10s): those are tiny GETs, this one uploads a
    whole base64-encoded JPEG (a few hundred KB) from Russia, where
    Cloudflare is known to be throttled (CLAUDE.md section 7, lần 8).
    A client-side timeout here does NOT guarantee the Worker's
    sendPhoto didn't still go through -- see the TimeoutError message
    below -- so it's worth waiting longer before giving up and risking
    a double post to real channel subscribers."""
    if not worker_url or not sync_secret:
        raise AnnounceError(
            "Chưa cài đặt đồng bộ: cần nhập Worker URL và Mã đồng bộ trước "
            "(tab \"Đơn hàng online\" → \"Cài đặt đồng bộ…\")."
        )

    product = get_product(conn, code)
    if product is None:
        raise AnnounceError("Không tìm thấy mặt hàng này.")
    if not product.get("image_filename"):
        raise AnnounceError("Mặt hàng chưa có ảnh -- thêm ảnh trước khi đăng lên kênh.")
    image_path = images_dir / product["image_filename"]
    if not image_path.exists():
        raise AnnounceError("File ảnh không có trên máy -- chọn lại ảnh cho mặt hàng này.")

    caption = build_caption(product)
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

    url = worker_url.rstrip("/") + "/channel/announce"
    body = json.dumps(
        {"code": code, "caption": caption, "imageBase64": image_b64, "filename": image_path.name}
    ).encode("utf-8")
    # Same User-Agent trick as online_orders.sync_from_bot/
    # supplier_invoices.sync_photos_from_bot -- Cloudflare's edge bot
    # protection blocks Python's default "Python-urllib/..." signature
    # with its own 403 before the Worker code ever runs.
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "X-Sync-Secret": sync_secret,
            "User-Agent": "ShopApp-ChannelAnnounce/1.0",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise AnnounceError(
                "Mã đồng bộ không đúng. Kiểm tra lại Mã đồng bộ trong app và SYNC_SECRET trên Cloudflare."
            ) from e
        if e.code == 502:
            raise AnnounceError(
                "Telegram từ chối ảnh này -- kiểm tra CHANNEL_CHAT_ID đúng chưa, và bot còn quyền "
                "\"Post messages\" trong kênh không, rồi thử lại."
            ) from e
        raise AnnounceError(
            f"Bot trả về lỗi (HTTP {e.code}). Có thể chưa cài đặt CHANNEL_CHAT_ID hoặc chưa deploy lại Worker "
            "(xem bot/README.md)."
        ) from e
    except urllib.error.URLError as e:
        raise AnnounceError(
            "Không kết nối được tới bot. Kiểm tra mạng (có thể cần VPN nếu đang ở Nga) rồi thử lại."
        ) from e
    except (TimeoutError, OSError) as e:
        raise AnnounceError(
            "Kết nối tới bot quá lâu -- CÓ THỂ TIN ĐÃ ĐĂNG THÀNH CÔNG dù máy chưa kịp nhận phản hồi "
            "(mạng chậm, nhất là ở Nga). Mở kênh kiểm tra trước khi bấm đăng lại, tránh đăng trùng."
        ) from e
    except ValueError as e:
        raise AnnounceError("Bot chưa hỗ trợ đăng lên kênh -- cần deploy lại Worker (xem bot/README.md).") from e

    set_channel_announced(conn, code, _now())
