"""Manifest bookkeeping for product photos under the site repo's
images/ folder -- shared by shop.tools.fetch_images (downloads via
Pillow, a dev-only tool never shipped with the app) and
shop.ui.dialogs' "Chọn ảnh từ máy..." button (decodes via Qt, the only
image library the packaged app actually carries). Neither of those
image-decoding paths is imported here -- this module only touches
images/manifest.json and the DB, never raw image bytes, so it's safe
for both to share.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from shop.core.products import set_image_filename

# Same thresholds shop.tools.fetch_images already validates against --
# kept here so both image sources (downloaded or picked from disk)
# apply one rule, not two that can drift apart.
MIN_SHORT_SIDE = 380
MAX_LONG_SIDE = 1200


def manifest_path(images_dir: Path) -> Path:
    return images_dir / "manifest.json"


def load_manifest(images_dir: Path) -> dict:
    path = manifest_path(images_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_manifest(images_dir: Path, manifest: dict) -> None:
    manifest_path(images_dir).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def record_image(
    conn,
    images_dir: Path,
    code: str,
    filename: str,
    size: tuple[int, int],
    source_url: str | None,
    source_page: str | None = None,
) -> None:
    """Record where a product's photo came from (images/manifest.json)
    and point the product row at it (products.image_filename) -- the
    bookkeeping common to every way a photo ends up on disk."""
    manifest = load_manifest(images_dir)
    manifest[code] = {
        "source_url": source_url,
        "source_page": source_page,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "size": list(size),
    }
    save_manifest(images_dir, manifest)
    set_image_filename(conn, code, filename)
