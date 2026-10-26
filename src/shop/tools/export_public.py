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

from shop.core.pricing import PUBLIC_MARKUP_PCT, bulk_price, unit_price
from shop.core.products import list_products
from shop.db.migrate import connect
from shop.paths import repo_root, site_repo_dir

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
    for p in list_products(conn, active_only=True):  # already name-sorted (shop.db.migrate's VNAME collation)
        price = unit_price(p["cost_price"], PUBLIC_MARKUP_PCT)
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
        if not p["in_stock"]:
            entry["in_stock"] = False
        if p["sale_until"]:
            entry["sale_until"] = p["sale_until"]
        if p["bulk_qty"]:
            entry["bulk_qty"] = p["bulk_qty"]
            entry["bulk_price"] = bulk_price(price, p["bulk_qty"])
        items.append(entry)

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "currency": "RUB",
        "items": items,
    }


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect()
    payload = build_payload(conn)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload['items'])} products to {out_path}")


if __name__ == "__main__":
    main()
