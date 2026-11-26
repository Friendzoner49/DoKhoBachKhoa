"""Export the public price list (no cost price — the markup percent
itself is also left out, so cost can't be back-calculated) as JSON for
the static price website.

Usage:
    uv run python -m shop.tools.export_public [output_path]

Default output: site/products.json (repo root). For actually publishing
the site, see shop.tools.publish_site instead.
"""
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from shop.core.community_links import parse_links_text
from shop.core.pricing import PUBLIC_MARKUP_PCT, effective_bulk_price, sale_unit_price
from shop.core.products import gallery_list, get_food_tab_always, list_products, order_deadline
from shop.core.stock import order_cutoff_ms, remaining
from shop.db.migrate import connect
from shop.paths import bot_sync_settings, community_links_text, repo_root, site_repo_dir

DEFAULT_OUT = repo_root() / "site" / "products.json"
DEFAULT_CATEGORY = "Khác"


def _image_ref(images_dir: Path, filename: str | None) -> str | None:
    """Only point the site at an image that's actually on disk, with a
    short content-hash query string -- so after the user asks for a
    specific photo to be swapped, the new file doesn't sit behind
    GitHub Pages' ~10 minute cache under the old, already-cached URL."""
    if not filename:
        return None
    path = images_dir / filename
    if not path.exists():
        return None
    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:8]
    return f"images/{filename}?v={digest}"


def build_payload(conn: sqlite3.Connection) -> dict:
    images_dir = site_repo_dir() / "images"
    items = []
    limited = False
    for p in list_products(conn, active_only=True):  # already name-sorted (shop.db.migrate's VNAME collation)
        price = sale_unit_price(p["cost_price"], PUBLIC_MARKUP_PCT, p["fixed_price"])
        entry = {
            "code": p["code"],
            "name": p["name"],
            "unit": p["unit"],
            "category": p["category"] or DEFAULT_CATEGORY,
            "price": price,
        }
        image = _image_ref(images_dir, p["image_filename"])
        if image:
            entry["image"] = image
        # "Quà tặng" items only (lần 38) -- extra photo angles + a long
        # description. Omitted entirely for the other 146 ordinary
        # products, so their JSON entries stay byte-identical to before.
        gallery = gallery_list(p)
        if gallery:
            all_refs = [image] + [_image_ref(images_dir, f) for f in gallery]
            seen = set()
            images_out = []
            for ref in all_refs:
                if ref and ref not in seen:
                    seen.add(ref)
                    images_out.append(ref)
            if images_out:
                entry["images"] = images_out
        if p["description"]:
            entry["description"] = p["description"]
        if p["ingredients"]:
            entry["ingredients"] = p["ingredients"]
        if not p["in_stock"]:
            entry["in_stock"] = False
        if p["sale_until"]:
            entry["sale_until"] = p["sale_until"]
            # Full instant with offset: web and bot close at the same moment
            # whatever time zone the visitor is in.
            entry["deadline"] = order_deadline(p).isoformat(timespec="seconds")
        # Size options of one dish (20/11/2026): the web merges every item
        # sharing a "group" into one card with a size picker. Only present
        # when set, so ordinary products stay byte-identical.
        if p["option_group"]:
            entry["group"] = p["option_group"]
            entry["option"] = p["option_label"] or p["name"]
        # Limited portions (26/11/2026): only for a dish with a limit.
        left = remaining(conn, p) if p["sale_until"] else None
        if left is not None:
            limited = True
            entry["stock_limit"] = p["stock_limit"]
            entry["remaining"] = left
            entry["stock_after"] = order_cutoff_ms(conn, p["stock_since"])
        if p["bulk_qty"] == 1:
            # Sold only as whole packs (e.g. a 5kg rice bag): every unit IS a
            # bulk pack, so show the bulk price as the price, no "Sỉ 1" line.
            entry["price"] = effective_bulk_price(price, 1, p["bulk_price_override"])
        elif p["bulk_qty"]:
            entry["bulk_qty"] = p["bulk_qty"]
            entry["bulk_price"] = effective_bulk_price(price, p["bulk_qty"], p["bulk_price_override"])
        items.append(entry)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "currency": "RUB",
        "items": items,
    }
    # Where the web asks the bot for the live number of portions left.
    worker_url = bot_sync_settings()[0] if limited else ""
    if worker_url:
        payload["stock_url"] = worker_url.rstrip("/") + "/stock"
    # Only present when the owner turned it on (see get_food_tab_always),
    # so the file stays as before otherwise.
    if get_food_tab_always(conn):
        payload["show_food_tab"] = True
    # Video buttons at the bottom of the page -- only when the owner listed some.
    community = parse_links_text(community_links_text())
    if community["links"]:
        payload["community"] = community
    return payload


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect()
    payload = build_payload(conn)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload['items'])} products to {out_path}")


if __name__ == "__main__":
    main()
