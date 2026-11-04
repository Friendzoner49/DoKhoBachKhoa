"""Publish the public price list to the SEPARATE public-site git repo
(shop.paths.site_repo_dir(), a sibling folder outside this project) and
push it.

This repo must never be the main K:\\705bot repo: its history holds the
cost-price spreadsheet, CLAUDE.md, and another client's notes, none of
which should ever reach a public remote. This script only ever writes
two files there: index.html and products.json.

Usage:
    uv run python -m shop.tools.publish_site

First-time setup (manual, one time):
    1. Create an empty public repo on GitHub.
    2. `git clone <url>` it to the path shop.paths.site_repo_dir() prints
       (or `git init` that folder and `git remote add origin <url>`).
    3. Do the FIRST push yourself from a terminal in that folder
       (`git push -u origin HEAD`, after adding something to commit) --
       Git Credential Manager may open a browser login window the first
       time, which would otherwise surface awkwardly from inside the
       app's button. After that, credentials are cached and the button
       just works.
This script refuses to touch a folder that isn't already a git repo, so
a push from the very first run never happens unattended.
"""
import json
import os
import subprocess
import sys
from datetime import date
from importlib import resources
from pathlib import Path

from shop.db.migrate import connect
from shop.paths import site_repo_dir
from shop.tools.export_public import build_payload

_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # fail fast instead of hanging the GUI on a missing credential
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _read_source_index() -> str:
    # importlib.resources, not a repo_root()-relative path: the same
    # lookup works whether running from source or from a PyInstaller
    # bundle, where repo_root() would point inside the bundle instead.
    return (resources.files("shop.site_template") / "index.html").read_text(encoding="utf-8")


def _run_git(args: list[str], cwd: Path, timeout: int = 60) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_GIT_ENV,
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout


def _needs_push(target: Path) -> bool:
    """True if there are commits not yet on the upstream branch -- also
    true when no upstream is configured at all, and true when an
    earlier push attempt failed partway (the commit landed locally but
    never reached GitHub), so a retry actually retries instead of
    reporting 'nothing changed'."""
    try:
        _run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=target)
    except RuntimeError:
        return True  # no upstream configured yet
    ahead = _run_git(["rev-list", "--count", "@{u}..HEAD"], cwd=target).strip()
    return ahead != "0"


def publish() -> str:
    """Returns a short Vietnamese status message; raises on a hard
    failure (e.g. git not found, push rejected)."""
    target = site_repo_dir()
    if not (target / ".git").exists():
        return (
            f"Thư mục '{target}' chưa phải git repo đã nối với GitHub.\n"
            "Tạo repo public trên GitHub rồi `git clone` nó vào đúng đường dẫn trên, "
            "hoặc `git init` + `git remote add origin <url>` tại đó, rồi thử lại."
        )

    conn = connect()
    new_payload = build_payload(conn)
    new_index = _read_source_index()

    target_json = target / "products.json"
    target_index = target / "index.html"

    items_changed = True
    if target_json.exists():
        try:
            old_payload = json.loads(target_json.read_text(encoding="utf-8"))
            items_changed = old_payload.get("items") != new_payload["items"]
        except json.JSONDecodeError:
            items_changed = True  # corrupt/unexpected content: republish to be safe

    index_changed = not target_index.exists() or target_index.read_text(encoding="utf-8") != new_index

    images_dir = target / "images"
    images_changed = images_dir.exists() and _run_git(
        ["status", "--porcelain", "--", "images"], cwd=target
    ).strip() != ""

    if items_changed or index_changed or images_changed:
        target_index.write_text(new_index, encoding="utf-8")
        target_json.write_text(json.dumps(new_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        add_args = ["index.html", "products.json"]
        if images_dir.exists():
            add_args.append("images")
        _run_git(["add", *add_args], cwd=target)
        staged = _run_git(["status", "--porcelain", "--", *add_args], cwd=target)
        if staged.strip():
            _run_git(["commit", "-m", f"Cap nhat bang gia {date.today().isoformat()}"], cwd=target)

    if not _needs_push(target):
        return "Giá và trang web không có gì thay đổi — không publish lại."

    _run_git(["push", "-u", "origin", "HEAD"], cwd=target, timeout=60)
    return f"Đã cập nhật và đẩy lên GitHub ({target})."


if __name__ == "__main__":
    # The Vietnamese status message can't encode to some Windows terminals'
    # legacy code page (cp1251 etc.); the GUI button path doesn't go
    # through print() at all, so this only affects running this file
    # directly from such a terminal.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    print(publish())
