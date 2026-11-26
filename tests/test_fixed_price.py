"""Pre-order dishes (20/11/2026): the owner sets the SALE price
(products.fixed_price) and types the real cost of one set into cost_price,
used only for profit. Every customer pays the fixed price, except
"Dùng nội bộ" who pays plain cost."""

import pytest

from shop.core.channel_announce import build_caption
from shop.core.customers import add_customer
from shop.core.invoices import add_line, create_invoice, get_invoice, invoice_profit, update_line
from shop.core.online_orders import (
    batch_shortage_report,
    close_batch,
    convert_to_invoice,
    list_online_orders,
    sync_from_bot,
)
from shop.core.pricing import sale_unit_price
from shop.core.products import get_product, set_fixed_price, set_sale_until, upsert_product
from shop.tools.export_public import build_payload

from test_online_orders import _fake_urlopen, _sample_order


def _seed_dish(conn, code="BGOI03", cost=200, price=350):
    upsert_product(conn, code, "Bánh gối – set 3 chiếc", "set", cost, source="test")
    set_sale_until(conn, code, "2099-12-31")
    set_fixed_price(conn, code, price)


def test_sale_unit_price_prefers_fixed_price():
    assert sale_unit_price(200, 7, 350) == 350
    assert sale_unit_price(200, 7, None) == 214  # 200 * 1.07


def test_set_fixed_price_rejects_zero_and_clears_with_none(conn):
    _seed_dish(conn)
    with pytest.raises(ValueError):
        set_fixed_price(conn, "BGOI03", 0)
    set_fixed_price(conn, "BGOI03", None)
    assert get_product(conn, "BGOI03")["fixed_price"] is None


def test_every_customer_pays_the_fixed_price_and_profit_uses_real_cost(conn):
    _seed_dish(conn, cost=200, price=350)
    cust = add_customer(conn, "Chi A", default_markup_pct=12)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "BGOI03", qty=2, markup_pct=12)

    line = get_invoice(conn, inv)["lines"][0]
    assert line["unit_price"] == 350  # not 200 * 1.12
    assert line["cost_price_snapshot"] == 200
    assert invoice_profit(conn, inv) == 2 * (350 - 200)


def test_editing_cost_on_a_draft_line_keeps_the_sale_price(conn):
    _seed_dish(conn, cost=200, price=350)
    inv = create_invoice(conn, add_customer(conn, "Chi B"))
    add_line(conn, inv, "BGOI03", qty=1)
    line_id = get_invoice(conn, inv)["lines"][0]["id"]

    update_line(conn, line_id, cost_price_value=260)

    line = get_invoice(conn, inv)["lines"][0]
    assert line["unit_price"] == 350
    assert invoice_profit(conn, inv) == 350 - 260


def test_internal_customer_pays_cost_not_the_fixed_price(conn):
    _seed_dish(conn, cost=200, price=350)
    owner = add_customer(conn, "Dùng nội bộ", default_markup_pct=0, internal=1)
    inv = create_invoice(conn, owner)
    add_line(conn, inv, "BGOI03", qty=1, markup_pct=0)
    assert get_invoice(conn, inv)["lines"][0]["unit_price"] == 200


def test_web_and_channel_show_the_fixed_price_without_leaking_the_field(conn):
    _seed_dish(conn, cost=200, price=350)
    item = next(i for i in build_payload(conn)["items"] if i["code"] == "BGOI03")
    assert item["price"] == 350
    assert "fixed_price" not in item
    assert "350 RUB" in build_caption(get_product(conn, "BGOI03"))


def test_edit_dialog_opens_for_an_existing_dish_and_keeps_its_price(qapp, conn):
    # Regression: the "Món ăn đặt trước" toggle slot ran before the price
    # spin existed, raising AttributeError when editing a dish.
    from shop.ui.dialogs import ProductDialog

    _seed_dish(conn, cost=84, price=350)
    dlg = ProductDialog(product=get_product(conn, "BGOI03"))
    assert not dlg.fixed_price_spin.isHidden()
    assert dlg.fixed_price_value() == 350
    dlg.grocery_radio.setChecked(True)
    assert dlg.fixed_price_spin.isHidden()
    assert dlg.fixed_price_value() is None


def test_online_order_for_a_dish_is_batched_and_invoiced_at_the_fixed_price(conn, monkeypatch):
    _seed_dish(conn, cost=200, price=350)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"orders": [_sample_order("sync:0001-111-ab", code="BGOI03", qty=2, name="Bánh gối", price=350)]}),
    )
    sync_from_bot(conn, "https://example.test", "secret")
    batch_id = close_batch(conn)
    # Cooked by the owner, never on a supplier invoice: not "short".
    assert batch_shortage_report(conn, batch_id) == []

    order_id = list_online_orders(conn)[0]["id"]
    invoice_id, dropped, excluded = convert_to_invoice(conn, order_id, add_customer(conn, "Khach", default_markup_pct=10))
    assert (dropped, excluded) == ([], [])
    line = get_invoice(conn, invoice_id)["lines"][0]
    assert (line["qty"], line["unit_price"], line["line_total"]) == (2, 350, 700)
