"""Best-effort OCR assist for reading a supplier invoice photo.

Uses the free, fully offline Tesseract engine -- never a paid API,
matching the project's zero-cost rule. Tesseract itself is a one-time
manual install (like Xcode/uv for the Mac build -- see CLAUDE.md); this
module only bundles the *language data* (rus+eng), so OCR quality never
depends on the user separately hunting down tessdata files, and stays
versioned with the rest of the app instead of living on only one machine.

rus+eng, not rus+vie: supplier invoices write Vietnamese names without
diacritics ("Banh Da Nem"), and Tesseract's Vietnamese model "corrects"
that into accented Vietnamese ("Bánh Đa Nem"), which then fails to match
anything in the catalog by substring/word overlap. Plain eng reads the
unaccented Latin text as-is, which is what's actually on the page.
"""
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

_CANDIDATE_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
]
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class OCRUnavailable(Exception):
    """Tesseract isn't installed, or failed to run. Every caller must
    catch this and fall back to manual entry -- there is no server-side
    fallback (would cost money and need internet)."""


def find_tesseract() -> Path | None:
    found = shutil.which("tesseract")
    if found:
        return Path(found)
    for candidate in _CANDIDATE_PATHS:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def is_available() -> bool:
    return find_tesseract() is not None


def _tessdata_dir() -> Path:
    return resources.files("shop.ocr")


def ocr_image(image_path: Path, lang: str = "rus+eng") -> str:
    """Returns the best-effort recognized text. Always needs a human to
    review it against the photo -- a hand-stamped, photographed invoice
    is never reliably perfect, especially the numeric columns."""
    exe = find_tesseract()
    if exe is None:
        raise OCRUnavailable(
            "Chưa cài Tesseract OCR trên máy này. Tải miễn phí tại "
            "https://github.com/UB-Mannheim/tesseract/wiki rồi thử lại, "
            "hoặc nhập tay trực tiếp."
        )
    try:
        result = subprocess.run(
            [str(exe), str(image_path), "stdout", "-l", lang, "--psm", "6", "--tessdata-dir", str(_tessdata_dir())],
            capture_output=True,
            timeout=30,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OCRUnavailable(f"Tesseract chạy lỗi: {exc}") from exc
    if result.returncode != 0:
        raise OCRUnavailable(result.stderr.decode("utf-8", errors="replace") or "Tesseract trả về lỗi không rõ.")
    return result.stdout.decode("utf-8", errors="replace")
