"""Where the app's data lives — resolved the same way in dev and once
packaged, so the catalog tools and the packaged app are never pointed at
two different databases.

A tiny config.json (DiBeKho's pattern) under the OS's per-user app-data
folder records the chosen data directory. First run picks a default and
writes it; a future Settings screen can let the user move it.
"""
import json
import os
import sys
from pathlib import Path

# TODO: rename once the project has a real name (also update CLAUDE.md).
APP_NAME = "ShopApp"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def config_path() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    else:
        base = Path.home() / ".config"
    return base / APP_NAME / "config.json"


def _default_data_dir() -> Path:
    if is_frozen():
        # Packaged app: a folder the user can see and back up, per DiBeKho's
        # "gon va de don" principle. A real build should also warn if this
        # lands inside a cloud-synced Documents folder.
        return Path.home() / "Documents" / APP_NAME
    # Running from source during development.
    return repo_root() / "data"


def _read_config() -> dict:
    cfg_path = config_path()
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_config(cfg: dict) -> None:
    cfg_path = config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _config_value(key: str, default_factory) -> Path:
    cfg = _read_config()
    if key in cfg:
        return Path(cfg[key])
    chosen = default_factory()
    cfg[key] = str(chosen)
    _write_config(cfg)
    return chosen


def data_dir() -> Path:
    # Escape hatch for self-tests/build verification: skips config.json
    # entirely, so a test run of a packaged exe on a dev machine can
    # never resolve to the real ledger in config.json.
    override = os.environ.get("SHOP_DATA_DIR")
    if override:
        return Path(override)
    return _config_value("data_dir", _default_data_dir)


def db_path() -> Path:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "shop.sqlite"


def supplier_invoices_dir() -> Path:
    """Where supplier-invoice photos are kept -- inside data_dir(), the
    same real-ledger folder as the database, never the code repo (see
    CLAUDE.md: a supplier invoice usually carries a phone number and the
    buyer's address)."""
    d = data_dir() / "supplier_invoices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default_site_repo_dir() -> Path:
    if is_frozen():
        return Path.home() / "Documents" / f"{APP_NAME}-site"
    return repo_root().parent / "705bot-site"


def site_repo_dir() -> Path:
    """Where the SEPARATE public website repo lives on disk (never the
    main repo_root() — that history holds cost prices and must never
    gain a public remote). Default: a sibling folder next to the main
    project in dev, or Documents\\ShopApp-site once packaged (repo_root()
    points inside the bundle when frozen, which isn't a sensible
    default). See shop.tools.publish_site."""
    return _config_value("site_repo_dir", _default_site_repo_dir)


def bot_sync_settings() -> tuple[str, str]:
    """(worker_url, sync_secret) for pulling online orders from the bot
    (shop.core.online_orders.sync_from_bot) -- empty strings until the
    user fills them in once via the "Đơn hàng online" tab's settings
    dialog. Stored as plain strings, not Path, unlike the rest of this
    module's _config_value()."""
    cfg = _read_config()
    return cfg.get("bot_sync_url", ""), cfg.get("bot_sync_secret", "")


def set_bot_sync_settings(worker_url: str, sync_secret: str) -> None:
    cfg = _read_config()
    cfg["bot_sync_url"] = worker_url
    cfg["bot_sync_secret"] = sync_secret
    _write_config(cfg)


def backups_dir() -> Path:
    """A local-only folder for automatic backups, deliberately separate
    from data_dir() (which may live in a user-visible, possibly
    cloud-synced Documents folder)."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    else:
        base = Path.home() / ".cache"
    d = base / APP_NAME / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d
