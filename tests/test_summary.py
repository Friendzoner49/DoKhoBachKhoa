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
