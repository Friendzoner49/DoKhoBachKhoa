"""Video buttons at the bottom of the public website (14/11/2026): the
owner's YouTube playlists (community events, vlogs). The owner pastes a
post in the same shape they already share in the Telegram group:

    Video cộng đồng (cập nhật khi có sự kiện mới).
    Giải bóng mẫu 2023 (https://bit.ly/DEMO2023)
    Vlog mẫu https://www.youtube.com/playlist?list=PLdemo123
    Trân trọng.

Every line holding an http(s) link becomes one button (the rest of the
line is its label); the first line without a link, if it comes before
any button, is the section title; every other line is ignored. The text
itself lives in config.json on this machine (shop.paths), not in code --
the repo is public.
"""
import re

_URL_RE = re.compile(r"https?://[^\s()<>\"']+")
DEFAULT_TITLE = "🎬 Video giải trí"
DEFAULT_LABEL = "Xem video"


def parse_links_text(text: str) -> dict:
    """{"title": str, "links": [{"title": str, "url": str}, ...]}."""
    title = None
    links = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _URL_RE.search(line)
        if not match:
            if title is None and not links:
                title = line
            continue
        url = match.group(0).rstrip(".,;")
        label = (line[: match.start()] + line[match.end():]).strip()
        # "Tên (link)" leaves an empty "()" behind; "Tên: link" a trailing colon.
        label = re.sub(r"\(\s*\)", "", label).strip(" -–—:|()")
        links.append({"title": label or DEFAULT_LABEL, "url": url})
    return {"title": _short_title(title) or DEFAULT_TITLE, "links": links}


def _short_title(title: str | None) -> str | None:
    """The group name shown on the web is kept short (14/11/2026, owner:
    "nhóm Giải trí tổng hợp"): a trailing "(…)" note and the final period
    are dropped -- "Giải trí tổng hợp (cập nhật khi có …)." -> "Giải trí tổng hợp"."""
    if not title:
        return None
    short = re.sub(r"\s*\([^()]*\)\s*\.?\s*$", "", title).rstrip(" .:")
    return short or title
