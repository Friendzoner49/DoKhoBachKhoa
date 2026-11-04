import pytest

from shop.core.customers import add_customer
from shop.core.invoices import (
    add_custom_line,
    add_line,
    cancel_invoice,
    create_invoice,
    delete_invoice,
    finalize_invoice,
    get_invoice,
    invoice_profit,
    remove_line,
    reopen_invoice,
    update_line,
)
from shop.core.products import upsert_product
from shop.core.summary import customer_debt


def _seed_product(conn, code="BADAM1", cost=350):
    upsert_product(conn, code, "Banh Da Me 350gr", "goi", cost, source="test")


def _seed_bulk_product(conn, code="MT0001", cost=59, bulk_qty=30):
    # cost=59, markup=0 -> unit_price=59, matching the shop's own price
    # list example for MT0001 used in test_pricing.py.
    upsert_product(conn, code, "My Tom Hao Hao", "goi", cost, bulk_qty=bulk_qty, source="test")


def test_add_line_defaults_price_from_customer_markup(conn):
    _seed_product(conn)
    cust = add_customer(conn, "Chi A", default_markup_pct=10)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "BADAM1", qty=2, markup_pct=10)

    data = get_invoice(conn, inv)
    assert data["lines"][0]["unit_price"] == 385  # 350 * 1.10
    assert data["total"] == 770


def test_add_custom_line_needs_no_catalog_product_and_counts_fully_as_profit(conn):
    cust = add_customer(conn, "Chi phi dich vu")
    inv = create_invoice(conn, cust)
    add_custom_line(conn, inv, "Phí vận chuyển", unit_price=200, qty=1)

    data = get_invoice(conn, inv)
    assert len(data["lines"]) == 1
    line = data["lines"][0]
    assert line["product_code"] == ""
    assert line["product_name_snapshot"] == "Phí vận chuyển"
    assert line["cost_price_snapshot"] == 0
    assert line["unit_price"] == 200
    assert line["line_total"] == 200
    assert data["total"] == 200

    finalize_invoice(conn, inv)
    assert invoice_profit(conn, inv) == 200  # no cost behind it -- the whole fee is profit
    assert customer_debt(conn, cust) == 200


def test_finalized_invoice_snapshot_survives_later_cost_change(conn):
    _seed_product(conn, cost=350)
    cust = add_customer(conn, "Chi B", default_markup_pct=10)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "BADAM1", qty=2, markup_pct=10)
    finalize_invoice(conn, inv)

    profit_before = invoice_profit(conn, inv)
    debt_before = customer_debt(conn, cust)

    # Cost goes up a lot after the invoice was finalized.
    _seed_product(conn, cost=1000)

    assert invoice_profit(conn, inv) == profit_before
    assert customer_debt(conn, cust) == debt_before


def test_draft_invoice_does_not_count_toward_debt(conn):
    _seed_product(conn)
    cust = add_customer(conn, "Chi C", default_markup_pct=10)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "BADAM1", qty=1, markup_pct=10)

    assert customer_debt(conn, cust) == 0  # still a draft, not finalized

    finalize_invoice(conn, inv)
    assert customer_debt(conn, cust) == 385


def test_cancelled_invoice_excluded_from_debt(conn):
    _seed_product(conn)
    cust = add_customer(conn, "Chi E", default_markup_pct=10)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "BADAM1", qty=1, markup_pct=10)
    finalize_invoice(conn, inv)
    assert customer_debt(conn, cust) == 385

    cancel_invoice(conn, inv)
    assert customer_debt(conn, cust) == 0


def test_reopen_invoice_returns_to_draft_and_drops_out_of_debt(conn):
    _seed_product(conn)
    cust = add_customer(conn, "Chi F", default_markup_pct=10)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "BADAM1", qty=1, markup_pct=10)
    finalize_invoice(conn, inv)
    assert customer_debt(conn, cust) == 385

    reopen_invoice(conn, inv)
    assert get_invoice(conn, inv)["status"] == "draft"
    assert customer_debt(conn, cust) == 0

    finalize_invoice(conn, inv)
    assert customer_debt(conn, cust) == 385


def test_delete_invoice_removes_an_empty_or_non_empty_draft(conn):
    _seed_product(conn)
    cust = add_customer(conn, "Chi G", default_markup_pct=10)
    inv = create_invoice(conn, cust)

    delete_invoice(conn, inv)  # empty draft: fine
    assert get_invoice(conn, inv) is None

    inv2 = create_invoice(conn, cust)
    add_line(conn, inv2, "BADAM1", qty=1, markup_pct=10)
    delete_invoice(conn, inv2)  # a draft with lines is fine too (28/10/2026)
    assert get_invoice(conn, inv2) is None


def test_delete_invoice_also_removes_a_cancelled_invoice(conn):
    _seed_product(conn)
    cust = add_customer(conn, "Chi H", default_markup_pct=10)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "BADAM1", qty=1, markup_pct=10)
    finalize_invoice(conn, inv)
    cancel_invoice(conn, inv)

    delete_invoice(conn, inv)
    assert get_invoice(conn, inv) is None


def test_delete_invoice_refuses_a_finalized_invoice(conn):
    _seed_product(conn)
    cust = add_customer(conn, "Chi K", default_markup_pct=10)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "BADAM1", qty=1, markup_pct=10)
    finalize_invoice(conn, inv)

    with pytest.raises(ValueError):
        delete_invoice(conn, inv)
    assert get_invoice(conn, inv) is not None  # still there, untouched


def test_editing_a_draft_lines_cost_changes_profit_not_debt(conn):
    # Regression test: a line's cost_price_snapshot used to be frozen at
    # add_line time with no way to correct it before finalizing, so a
    # supplier price change that arrives between "paste the order" and
    # "finalize" silently produced a stale profit number.
    _seed_product(conn, cost=350)
    cust = add_customer(conn, "Chi I", default_markup_pct=10)
    inv = create_invoice(conn, cust)
    line_id = add_line(conn, inv, "BADAM1", qty=1, markup_pct=10)  # unit_price 385, cost snapshot 350

    update_line(conn, line_id, cost_price_value=500)  # supplier's cost went up before finalizing
    finalize_invoice(conn, inv)

    assert invoice_profit(conn, inv) == 385 - 500  # -115, uses the corrected cost
    assert customer_debt(conn, cust) == 385  # debt only depends on unit_price/line_total, unaffected


def test_add_line_at_bulk_qty_adds_a_linked_discount_line(conn):
    # "Tôi muốn áp dụng thật chứ, tôi không buôn bán gian dối" (26/10/2026):
    # the website's "Lấy sỉ ×N" button must translate into a real discount
    # on the invoice, not just a number shown on the catalog page.
    _seed_bulk_product(conn)
    cust = add_customer(conn, "Chi Si", default_markup_pct=0)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "MT0001", qty=30, markup_pct=0)

    data = get_invoice(conn, inv)
    assert len(data["lines"]) == 2
    main, discount = data["lines"]
    assert main["product_code"] == "MT0001"
    assert main["unit_price"] == 59
    assert main["line_total"] == 1770
    assert discount["product_code"] == ""
    assert discount["unit_price"] == -35
    assert discount["line_total"] == -35
    assert "Chiết khấu sỉ" in discount["product_name_snapshot"]
    assert data["total"] == 1735  # == bulk_price(59, 30) from the public price list


def test_add_line_below_bulk_qty_has_no_discount_line(conn):
    _seed_bulk_product(conn)
    cust = add_customer(conn, "Chi Le", default_markup_pct=0)
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "MT0001", qty=29, markup_pct=0)

    data = get_invoice(conn, inv)
    assert len(data["lines"]) == 1
    assert data["total"] == 59 * 29


def test_editing_qty_past_the_bulk_threshold_adds_the_discount_line(conn):
    _seed_bulk_product(conn)
    cust = add_customer(conn, "Chi Tang", default_markup_pct=0)
    inv = create_invoice(conn, cust)
    line_id = add_line(conn, inv, "MT0001", qty=1, markup_pct=0)
    assert len(get_invoice(conn, inv)["lines"]) == 1  # no discount yet

    update_line(conn, line_id, qty=30)

    data = get_invoice(conn, inv)
    assert len(data["lines"]) == 2
    assert data["total"] == 1735


def test_editing_qty_back_below_the_bulk_threshold_removes_the_discount_line(conn):
    _seed_bulk_product(conn)
    cust = add_customer(conn, "Chi Giam", default_markup_pct=0)
    inv = create_invoice(conn, cust)
    line_id = add_line(conn, inv, "MT0001", qty=30, markup_pct=0)
    assert len(get_invoice(conn, inv)["lines"]) == 2

    update_line(conn, line_id, qty=5)

    data = get_invoice(conn, inv)
    assert len(data["lines"]) == 1
    assert data["total"] == 59 * 5


def test_removing_the_main_line_also_removes_its_linked_bulk_discount(conn):
    _seed_bulk_product(conn)
    cust = add_customer(conn, "Chi Xoa", default_markup_pct=0)
    inv = create_invoice(conn, cust)
    line_id = add_line(conn, inv, "MT0001", qty=30, markup_pct=0)
    assert len(get_invoice(conn, inv)["lines"]) == 2

    remove_line(conn, line_id)

    assert get_invoice(conn, inv)["lines"] == []  # no orphaned discount line left behind


def test_bulk_discount_reduces_profit_by_the_discount_amount(conn):
    _seed_bulk_product(conn, cost=50)
    cust = add_customer(conn, "Chi Loi Nhuan")  # default markup 7%
    inv = create_invoice(conn, cust)
    add_line(conn, inv, "MT0001", qty=30)
    finalize_invoice(conn, inv)

    data = get_invoice(conn, inv)
    main = next(line for line in data["lines"] if line["product_code"] == "MT0001")
    discount_line = next(line for line in data["lines"] if line["product_code"] == "")
    expected_profit = (main["unit_price"] - 50) * 30 + discount_line["line_total"]
    assert invoice_profit(conn, inv) == expected_profit
