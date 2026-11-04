"""Wipe all TRANSACTIONAL data (customers, invoices, payments, supplier
invoices, online orders) back to empty, while keeping the product
catalog (cost prices, images, categories) and the learned supplier
name-matching aliases untouched -- those took real work to set up and
are reference data, not "usage" data. For clearing out test/demo
entries made before the shop started using the system for real, not a
routine operation (see CLAUDE.md mục 7).

Qt-free like every other shop.core module -- shop.ui.settings_page is
where this gets a confirmation dialog.
"""
import sqlite3

from shop.core.online_orders import set_sync_floor

# Order matters: PRAGMA foreign_keys = ON (see shop.db.migrate.connect),
# and only online_order_lines -> online_orders is ON DELETE CASCADE --
# everything else must be deleted child-before-parent by hand.
_TABLES_IN_DELETE_ORDER = [
    "online_orders",  # cascades online_order_lines
    "order_batches",  # online_orders.batch_id -> here; must go after online_orders, before supplier_invoices (see migration 007)
    "telegram_customer_links",
    "invoice_lines",
    "invoices",
    "payments",
    "supplier_invoice_lines",
    "supplier_invoices",
    "customers",
]

# Shown to the user before they confirm -- not every deleted table, just
# the ones a human would recognize and want a count of.
_COUNTED_TABLES = ["customers", "invoices", "payments", "supplier_invoices", "online_orders"]


def transactional_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in _COUNTED_TABLES}


def reset_transactional_data(conn: sqlite3.Connection) -> None:
    for table in _TABLES_IN_DELETE_ORDER:
        conn.execute(f"DELETE FROM {table}")
    conn.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({','.join('?' * len(_TABLES_IN_DELETE_ORDER))})", _TABLES_IN_DELETE_ORDER)
    # Without this, the next "Đồng bộ ngay" would immediately re-pull
    # every pre-reset test order still sitting in the bot's KV (90-day
    # TTL) -- a reset must actually stay reset. See
    # online_orders.set_sync_floor's docstring.
    set_sync_floor(conn)
    conn.commit()
