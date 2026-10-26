"""Turn a local image file the user picked in the app into a product
photo for the website -- the Qt-based counterpart to
shop.tools.fetch_images.save_product_image() (which downloads via
Pillow, a dev-only tool never shipped with the app). PySide6 is already
a hard dependency of the shipped app, so this adds no packaging weight,
unlike Pillow -- see pyproject.toml's note on why Pillow stays dev-only.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from shop.core.product_images import MAX_LONG_SIDE, MIN_SHORT_SIDE, record_image
from shop.paths import site_repo_dir


class LocalImageError(Exception):
    pass


def apply_local_image(conn, code: str, source_path: Path) -> str:
    """Validate `source_path` (a file the user picked), cap its longer
    side at MAX_LONG_SIDE (never upscale), save it as images/<code>.jpg
    in the site repo, record it in images/manifest.json, and point the
    product's image_filename at it. Returns the filename. Raises
    LocalImageError (Vietnamese message, shown directly in a dialog) on
    anything that makes the image unusable."""
    img = QImage(str(source_path))
    if img.isNull():
        raise LocalImageError("Không đọc được file ảnh này -- có thể file bị hỏng hoặc không đúng định dạng ảnh.")

    w, h = img.width(), img.height()
    if min(w, h) < MIN_SHORT_SIDE:
        raise LocalImageError(f"Ảnh quá nhỏ ({w}x{h}px) -- cạnh ngắn cần tối thiểu {MIN_SHORT_SIDE}px để hiển thị rõ trên website.")

    if max(w, h) > MAX_LONG_SIDE:
        img = img.scaled(
            MAX_LONG_SIDE, MAX_LONG_SIDE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )

    images_dir = site_repo_dir() / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{code}.jpg"
    if not img.convertToFormat(QImage.Format.Format_RGB32).save(str(images_dir / filename), "JPG", quality=88):
        raise LocalImageError("Lưu ảnh thất bại -- thử lại hoặc chọn file khác.")

    record_image(conn, images_dir, code, filename, (img.width(), img.height()), source_url=f"Chọn từ máy: {source_path.name}")
    return filename
