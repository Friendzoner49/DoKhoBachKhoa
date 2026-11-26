"""Limited portions of a pre-order dish (26/11/2026)."""
from datetime import datetime

import pytest

from shop.core import stock
from shop.core.customers import add_customer
from shop.core.invoices import add_line, create_invoice
from shop.core.online_orders import convert_to_invoice, list_online_orders, sync_from_bot
from shop.core.products import get_product, set_fixed_price, set_sale_until, upsert_product
from shop.tools import export_public

from test_online_orders import _fake_urlopen, _sample_order


@pytest.fixture(autouse=True)
def _worker_url(monkeypatch):
    monkeypatch.setattr(export_public, "bot_sync_settings", lambda: ("https://bot.example/", "s"))


def _dish(conn, limit=8):
    upsert_product(conn, "XOI", "Xôi xéo", "xuất", 0, source="test")
    set_sale_until(conn, "XOI", "2099-12-31")
    set_fixed_price(conn, "XOI", 300)
    stock.set_stock_limit(conn, "XOI", limit)


def _order(conn, monkeypatch, qty=2):
    order = _sample_order("sync:4000000000000-555-abcd", chat_id=555, code="XOI", qty=qty, name="Xôi xéo", price=300)
    order["created_at"] = "2099-01-01T10:00:00.000Z"
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"orders": [order]}))
    sync_from_bot(conn, "https://bot.example", "s")
    return list_online_orders(conn)[0]


def _left(conn):
    return stock.remaining(conn, get_product(conn, "XOI"))


def test_order_of_two_leaves_six_and_conversion_is_not_counted_twice(conn, monkeypatch):
    _dish(conn)
    assert _left(conn) == 8
    order = _order(conn, monkeypatch)
    assert _left(conn) == 6
    convert_to_invoice(conn, order["id"], add_customer(conn, "Chị A"))
    assert _left(conn) == 6


def test_manual_invoice_counts_and_cancelled_order_does_not(conn, monkeypatch):
    _dish(conn)
    order = _order(conn, monkeypatch)
    inv = create_invoice(conn, add_customer(conn, "Anh B"))
    add_line(conn, inv, "XOI", qty=1, markup_pct=7)
    assert _left(conn) == 5
    conn.execute("UPDATE online_orders SET status = 'da_huy' WHERE id = ?", (order["id"],))
    assert _left(conn) == 7


def test_export_publishes_counts_and_a_time_never_the_order_key(conn, monkeypatch):
    _dish(conn)
    _order(conn, monkeypatch)
    payload = export_public.build_payload(conn)
    item = payload["items"][0]
    assert (item["stock_limit"], item["remaining"], item["stock_after"]) == (8, 6, 4000000000000)
    assert payload["stock_url"] == "https://bot.example/stock"
    assert "555" not in str(payload)


def test_unlimited_dish_has_no_stock_keys(conn):
    _dish(conn, limit=None)
    payload = export_public.build_payload(conn)
    assert not {"stock_limit", "remaining", "stock_after"} & set(payload["items"][0])
    assert "stock_url" not in payload


def test_new_round_only_when_an_expired_dish_is_reopened(conn):
    _dish(conn)
    conn.execute("UPDATE products SET stock_since = '2000-01-01T00:00:00+00:00'")
    stock.set_stock_limit(conn, "XOI", 10, previous={"sale_until": "2099-12-31"})
    assert get_product(conn, "XOI")["stock_since"].startswith("2000")
    # closed at 12:00, reopened the same afternoon
    closed = {"sale_until": "2026-11-26", "sale_until_time": "12:00"}
    stock.set_stock_limit(conn, "XOI", 10, previous=closed, now=datetime(2026, 11, 26, 13, 0).astimezone())
    assert get_product(conn, "XOI")["stock_since"] > "2026-11-25"


def test_zero_is_rejected(conn):
    _dish(conn)
    with pytest.raises(ValueError):
        stock.set_stock_limit(conn, "XOI", 0)
