"""Download and validate one product photo at a time for the public
website, and record it (DB + a manifest in the site repo) so a later
"replace this one image" request is a single call, not a re-run of a
146-product search.

This is a developer-side tool only -- Pillow is a dev dependency (see
pyproject.toml) and this module is never imported by the packaged app.

Usage (one product):
    uv run python -m shop.tools.fetch_images CODE "https://.../photo.jpg" "https://source-page/"

The actual bulk sourcing (searching for a good photo per product) isn't
done here -- that's a research step (WebSearch/WebFetch/browsing),
typically run by an agent across many products at once. This module is
the one place that actually touches disk/DB, so every one of those
downloads is validated and recorded the same way.
"""
import sys
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from shop.core.product_images import MAX_LONG_SIDE, MIN_SHORT_SIDE, record_image
from shop.core.products import get_product
from shop.db.migrate import connect
from shop.paths import site_repo_dir

MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024
TIMEOUT = 20
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


class FetchImageError(Exception):
    pass


def _download(url: str) -> bytes:
    # Some source URLs carry a non-ASCII character (seen from a retailer's
    # product slug), which http.client's header encoder rejects outright
    # -- harmless to drop the Referer for that one request, since it's
    # only there to satisfy basic anti-hotlink checks, not a requirement.
    try:
        req = Request(url, headers={"User-Agent": _UA, "Referer": url})
        with urlopen(req, timeout=TIMEOUT) as resp:
            data = resp.read(MAX_DOWNLOAD_BYTES + 1)
    except UnicodeEncodeError:
        req = Request(url, headers={"User-Agent": _UA})
        with urlopen(req, timeout=TIMEOUT) as resp:
            data = resp.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise FetchImageError(f"download exceeds {MAX_DOWNLOAD_BYTES} bytes, refusing")
    return data


def save_product_image(conn, code: str, source_url: str, source_page: str | None = None) -> str:
    """Download `source_url`, validate it's a real, large-enough image,
    cap its longer side at MAX_LONG_SIDE (never upscale), save it as
    images/<code>.jpg in the site repo, record it in images/manifest.json,
    and point the product's image_filename at it. Returns the filename.
    Raises FetchImageError on anything that makes the image unusable."""
    from PIL import Image, UnidentifiedImageError

    product = get_product(conn, code)
    if product is None:
        raise FetchImageError(f"no such product code: {code}")

    try:
        raw = _download(source_url)
    except Exception as exc:  # network/HTTP errors of many shapes
        raise FetchImageError(f"download failed: {exc}") from exc

    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except UnidentifiedImageError as exc:
        raise FetchImageError("downloaded content is not a decodable image") from exc

    img = img.convert("RGB")  # drop alpha/CMYK/palette surprises before saving as jpeg
    w, h = img.size
    if min(w, h) < MIN_SHORT_SIDE:
        raise FetchImageError(f"image too small ({w}x{h}), need >= {MIN_SHORT_SIDE}px on the short side")

    if max(w, h) > MAX_LONG_SIDE:
        scale = MAX_LONG_SIDE / max(w, h)
        img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)

    images_dir = site_repo_dir() / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{code}.jpg"
    img.save(images_dir / filename, "JPEG", quality=88, optimize=True)

    record_image(conn, images_dir, code, filename, img.size, source_url, source_page)
    return filename


def main():
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        sys.exit(1)
    code, url = sys.argv[1], sys.argv[2]
    source_page = sys.argv[3] if len(sys.argv) == 4 else None

    conn = connect()
    try:
        filename = save_product_image(conn, code, url, source_page)
    except FetchImageError as exc:
        print(f"FAILED {code}: {exc}")
        sys.exit(1)
    print(f"OK {code} -> {filename}")


if __name__ == "__main__":
    main()
