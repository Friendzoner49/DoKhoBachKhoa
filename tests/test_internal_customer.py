"""Tests for the internal customer, wholesale conversion, learned matches and
the wholesale-price exception. Fake codes and prices only (public repo)."""
from shop.core import invoices as inv
from shop.core.customers import add_customer, get_customer
from shop.core.products import get_product, set_bulk_price_override, upsert_product
from shop.core.summary import total_customer_debt, total_profit


def test_internal_customer_priced_at_cost_and_excluded_from_totals(conn):
    upsert_product(conn, "TST01", "Hàng thử", "gói", 100, source="test")
    me = add_customer(conn, "Chủ shop", default_markup_pct=0, internal=1)
    other = add_customer(conn, "Khách thử", default_markup_pct=10)
    assert get_customer(conn, me)["internal"] == 1

    for cid, markup in ((me, 0), (other, 10)):
        invoice_id = inv.create_invoice(conn, cid)
        inv.add_line(conn, invoice_id, "TST01", qty=2, markup_pct=markup)
        inv.finalize_invoice(conn, invoice_id)

    assert total_customer_debt(conn) == 220  # only the other customer: 2 x 110
    assert total_profit(conn) == 20


def test_wholesale_invoice_price_is_converted_to_per_kg_but_per_piece_stays(conn):
    from shop.core.supplier_invoices import (
        add_line, auto_convert_wholesale, create_invoice, list_lines, suggest_wholesale_conversion,
    )

    upsert_product(conn, "RICE1", "Gạo thử 5kg", "KG", 200, bulk_qty=5, source="t")
    upsert_product(conn, "NOOD1", "Mì thử", "gói", 40, bulk_qty=30, source="t")
    assert suggest_wholesale_conversion(conn, "RICE1", 1000) == 5.0  # 1000 per bag -> 200/kg
    assert suggest_wholesale_conversion(conn, "RICE1", 200) == 1.0  # already per kg
    assert suggest_wholesale_conversion(conn, "NOOD1", 40) == 1.0  # carton product priced per piece

    invoice_id = create_invoice(conn)
    add_line(conn, invoice_id, raw_name="gao", raw_qty=3, raw_unit="шт", raw_unit_price=1000, matched_code="RICE1")
    add_line(conn, invoice_id, raw_name="mi", raw_qty=60, raw_unit="шт", raw_unit_price=40, matched_code="NOOD1")
    assert [l["matched_code"] for l in auto_convert_wholesale(conn, invoice_id)] == ["RICE1"]
    assert {l["matched_code"]: l["unit_conversion"] for l in list_lines(conn, invoice_id)} == {"RICE1": 5.0, "NOOD1": 1.0}


def test_confirmed_matches_are_learned_and_reused_for_new_ai_reads(conn):
    from shop.core.supplier_invoices import add_line, create_invoice, find_known_match, update_line

    upsert_product(conn, "RICE1", "Gạo thử 5kg", "KG", 200, bulk_qty=5, source="t")
    upsert_product(conn, "SAUC1", "Nước sốt thử", "chai", 600, source="t")

    invoice_id = create_invoice(conn)
    line = add_line(
        conn, invoice_id, "Ris zhasmin premium sort 5 kg Vietnam", 3, "шт", 1000,
        raw_name_ru="Рис жасмин премиум сорт 5 кг Вьетнам",
    )
    update_line(conn, line, matched_code="RICE1")  # the owner's confirmation

    # same product spelled a little differently by the AI next time -> matched + wholesale-converted
    hit = find_known_match(conn, "Ris zhasmin premium sort 5kg Vietnam", "Рис жасмин премиум сорт 5 кг, Вьетнам", 1000)
    assert hit == {"code": "RICE1", "unit_conversion": 5.0}
    # an unrelated product is NOT guessed
    assert find_known_match(conn, "Sous ustritsy 2.4l", "Соус устричный 2,4 л", 600) is None


def test_bulk_override_on_invoices_exports_and_internal_customer(conn):
    from shop.tools.export_public import build_payload

    upsert_product(conn, "RICE1", "Gạo thử 5kg", "KG", 200, bulk_qty=5, source="t")
    set_bulk_price_override(conn, "RICE1", 1000)
    # a later price import/apply must not wipe the exception
    upsert_product(conn, "RICE1", "Gạo thử 5kg", "KG", 210, bulk_qty=5, source="supplier")
    assert get_product(conn, "RICE1")["bulk_price_override"] == 1000

    # public price 7%: the published bag price is the exception; the raw override is not exported
    item = next(i for i in build_payload(conn)["items"] if i["code"] == "RICE1")
    assert item["bulk_price"] == 1000
    assert "bulk_price_override" not in item

    normal = add_customer(conn, "Khách thử", default_markup_pct=7)
    me = add_customer(conn, "Chủ shop", default_markup_pct=0, internal=1)
    totals, normal_invoice, normal_line = {}, None, None
    for cid, markup in ((normal, 7), (me, 0)):
        invoice_id = inv.create_invoice(conn, cid)
        line_id = inv.add_line(conn, invoice_id, "RICE1", qty=5, markup_pct=markup)
        inv.finalize_invoice(conn, invoice_id) if cid == me else None
        totals[cid] = sum(l["line_total"] for l in inv.get_lines(conn, invoice_id))
        if cid == normal:
            normal_invoice, normal_line = invoice_id, line_id
    assert totals[normal] == 1000  # the bag price, not 5 x 225
    assert totals[me] == 1050  # internal: plain cost 5 x 210, no bag discount

    # editing the quantity on a draft line keeps using the exception (2 bags)
    inv.update_line(conn, normal_line, qty=10)
    lines = inv.get_lines(conn, normal_invoice)
    assert sum(l["line_total"] for l in lines) == 2000
    assert any(l["product_name_snapshot"].startswith("Chiết khấu sỉ —") for l in lines)


def test_below_cost_overrides_are_reported(conn):
    from shop.core.supplier_invoices import below_cost_overrides

    upsert_product(conn, "RICE1", "Gạo thử 5kg", "KG", 200, bulk_qty=5, source="t")
    set_bulk_price_override(conn, "RICE1", 1000)
    assert below_cost_overrides(conn, ["RICE1"]) == []  # 1000 >= 5 x 200
    upsert_product(conn, "RICE1", "Gạo thử 5kg", "KG", 230, bulk_qty=5, source="supplier")  # cost rises
    assert [x["code"] for x in below_cost_overrides(conn, ["RICE1"])] == ["RICE1"]


def test_internal_customer_never_owes_anything(conn):
    from shop.core.summary import customer_debt

    upsert_product(conn, "TST01", "Hàng thử", "gói", 100, source="test")
    me = add_customer(conn, "Chủ shop", default_markup_pct=0, internal=1, opening_balance=500)
    invoice_id = inv.create_invoice(conn, me)
    inv.add_line(conn, invoice_id, "TST01", qty=2, markup_pct=0)
    inv.finalize_invoice(conn, invoice_id)
    assert customer_debt(conn, me) == 0  # considered paid; no "Ghi nhận thanh toán" needed
