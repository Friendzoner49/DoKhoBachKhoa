"""Turn a local image file the user picked in the app into a product
photo for the website -- the Qt-based counterpart to
shop.tools.fetch_images.save_product_image() (which downloads via
Pillow, a dev-only tool never shipped with the app). PySide6 is already
a hard dependency of the shipped app, so this adds no packaging weight,
unlike Pillow -- see pyproject.toml's note on why Pillow stays dev-only.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader

from shop.core.product_images import MAX_LONG_SIDE, MIN_SHORT_SIDE, record_image
from shop.core.products import gallery_list, get_product, set_gallery_filenames
from shop.paths import site_repo_dir


class LocalImageError(Exception):
    pass


def _read_oriented(source_path: Path) -> QImage:
    """QImage(path) ignores EXIF orientation -- a camera photo (e.g. an
    iPhone JPG, "chụp dọc" flagged via EXIF rather than physically
    rotated pixels) would silently come out sideways. QImageReader with
    autoTransform applies that rotation before any further processing."""
    reader = QImageReader(str(source_path))
    reader.setAutoTransform(True)
    return reader.read()


def _prepare(source_path: Path) -> QImage:
    """Read (EXIF-rotated), validate, and cap the longer side at MAX_LONG_SIDE (never upscale)."""
    img = _read_oriented(source_path)
    if img.isNull():
        raise LocalImageError("Không đọc được file ảnh này -- có thể file bị hỏng hoặc không đúng định dạng ảnh.")
    w, h = img.width(), img.height()
    if min(w, h) < MIN_SHORT_SIDE:
        raise LocalImageError(f"Ảnh quá nhỏ ({w}x{h}px) -- cạnh ngắn cần tối thiểu {MIN_SHORT_SIDE}px để hiển thị rõ trên website.")
    if max(w, h) > MAX_LONG_SIDE:
        img = img.scaled(
            MAX_LONG_SIDE, MAX_LONG_SIDE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    return img


def _save_jpg(img: QImage, images_dir: Path, filename: str) -> None:
    images_dir.mkdir(parents=True, exist_ok=True)
    if not img.convertToFormat(QImage.Format.Format_RGB32).save(str(images_dir / filename), "JPG", quality=88):
        raise LocalImageError("Lưu ảnh thất bại -- thử lại hoặc chọn file khác.")


def apply_local_image(conn, code: str, source_path: Path) -> str:
    """Validate `source_path` (a file the user picked), cap its longer
    side at MAX_LONG_SIDE (never upscale), save it as images/<code>.jpg
    in the site repo, record it in images/manifest.json, and point the
    product's image_filename at it. Returns the filename. Raises
    LocalImageError (Vietnamese message, shown directly in a dialog) on
    anything that makes the image unusable."""
    img = _prepare(source_path)
    images_dir = site_repo_dir() / "images"
    filename = f"{code}.jpg"
    _save_jpg(img, images_dir, filename)

    record_image(conn, images_dir, code, filename, (img.width(), img.height()), source_url=f"Chọn từ máy: {source_path.name}")
    return filename


def apply_gallery_photo(conn, code: str, source_path: Path) -> str:
    """Same validate/resize/save as apply_local_image, but appends to
    the product's gallery (products.gallery_filenames) instead of
    replacing the single cover photo -- for "Quà tặng" items that need
    every angle visible (lần 38), not the 1-photo-per-product norm.
    Filename pattern "{code}-g{n}.jpg", n = 1-based, next free slot."""
    img = _prepare(source_path)
    images_dir = site_repo_dir() / "images"

    existing = gallery_list(get_product(conn, code))
    next_n = len(existing) + 1
    filename = f"{code}-g{next_n}.jpg"
    while (images_dir / filename).exists():
        next_n += 1
        filename = f"{code}-g{next_n}.jpg"

    _save_jpg(img, images_dir, filename)

    set_gallery_filenames(conn, code, existing + [filename])
    return filename


def remove_gallery_photo(conn, code: str, filename: str) -> None:
    existing = gallery_list(get_product(conn, code))
    if filename not in existing:
        return
    set_gallery_filenames(conn, code, [f for f in existing if f != filename])
    path = site_repo_dir() / "images" / filename
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass  # best-effort -- a locked/missing file must not block removing the DB reference
