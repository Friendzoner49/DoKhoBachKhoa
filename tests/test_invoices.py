from shop.core.customers import add_customer
from shop.core.invoices import (
    add_custom_line,
    add_line,
    cancel_invoice,
    create_invoice,
    delete_draft_invoice,
    finalize_invoice,
    get_invoice,
    invoice_profit,
    reopen_invoice,
    update_line,
)
from shop.core.products import upsert_product
from shop.core.summary import customer_debt


def _seed_product(conn, code="BADAM1", cost=350):
    upsert_product(conn, code, "Banh Da Me 350gr", "goi", cost, source="test")


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


def test_delete_draft_invoice_requires_no_lines(conn):
    _seed_product(conn)
    cust = add_customer(conn, "Chi G", default_markup_pct=10)
    inv = create_invoice(conn, cust)

    delete_draft_invoice(conn, inv)  # empty draft: fine
    assert get_invoice(conn, inv) is None

    inv2 = create_invoice(conn, cust)
    add_line(conn, inv2, "BADAM1", qty=1, markup_pct=10)
    try:
        delete_draft_invoice(conn, inv2)
        assert False, "expected ValueError for a draft with lines"
    except ValueError:
        pass


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
