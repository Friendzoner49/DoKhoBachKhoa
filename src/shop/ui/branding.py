"""Shared lookup for the BachHoa705 mark -- bundled as plain package data
(same mechanism as shop.ocr's traineddata files), so it resolves the same
way in dev and once frozen. Used by app.py (window/taskbar icon) and
dashboard_page.py (header band); a missing/corrupt file must never crash
either caller.
"""
from importlib import resources
from pathlib import Path


def icon_path(filename: str = "icon.png") -> Path | None:
    try:
        with resources.as_file(resources.files("shop.ui") / filename) as path:
            return path if path.exists() else None
    except (FileNotFoundError, OSError):
        return None
