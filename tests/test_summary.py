from shop.core.customers import add_customer
from shop.core.invoices import add_line, create_invoice, finalize_invoice
from shop.core.payments import add_payment, delete_payment, list_payments
from shop.core.products import upsert_product
from shop.core.summary import customer_debt


def test_debt_combines_opening_balance_invoices_and_payments(conn):
    upsert_product(conn, "BADAM1", "Banh Da Me", "goi", 350, source="test")
    cust = add_customer(conn, "Chi D", default_markup_pct=10, opening_balance=1000)

    inv = create_invoice(conn, cust)
    add_line(conn, inv, "BADAM1", qty=2, markup_pct=10)  # 770
    finalize_invoice(conn, inv)

    add_payment(conn, cust, 500)

    # 1000 (opening) + 770 (invoice) - 500 (payment) = 1270
    assert customer_debt(conn, cust) == 1270


def test_deleting_a_payment_restores_debt(conn):
    upsert_product(conn, "BADAM1", "Banh Da Me", "goi", 350, source="test")
    cust = add_customer(conn, "Chi H", default_markup_pct=10, opening_balance=1000)

    payment_id = add_payment(conn, cust, 500)
    assert customer_debt(conn, cust) == 500  # 1000 - 500

    delete_payment(conn, payment_id)
    assert customer_debt(conn, cust) == 1000
    assert list_payments(conn, cust) == []


def test_unpaid_invoices_allocates_payments_oldest_first(conn):
    from shop.core import invoices as inv
    from shop.core.customers import add_customer
    from shop.core.payments import add_payment
    from shop.core.products import upsert_product
    from shop.core.summary import unpaid_invoices

    upsert_product(conn, "TST01", "Hàng thử", "gói", 100, source="t")
    cid = add_customer(conn, "Khách thử", default_markup_pct=0)
    ids = []
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        invoice_id = inv.create_invoice(conn, cid, invoice_date=day)
        inv.add_line(conn, invoice_id, "TST01", qty=3, markup_pct=0)  # 300 each
        inv.finalize_invoice(conn, invoice_id)
        ids.append(invoice_id)
    assert [u["remaining"] for u in unpaid_invoices(conn, cid)] == [300, 300, 300]
    add_payment(conn, cid, 450)  # settles #1 and half of #2
    assert [(u["id"], u["remaining"]) for u in unpaid_invoices(conn, cid)] == [(ids[1], 150), (ids[2], 300)]
