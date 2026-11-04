import pytest

from shop.core.customers import add_customer, delete_customer, get_customer
from shop.core.invoices import add_line, create_invoice, finalize_invoice
from shop.core.payments import add_payment
from shop.core.products import upsert_product


def test_delete_customer_removes_one_with_no_history(conn):
    customer_id = add_customer(conn, "Khach moi")
    delete_customer(conn, customer_id)
    assert get_customer(conn, customer_id) is None


def test_delete_customer_refuses_one_with_an_invoice(conn):
    upsert_product(conn, "BADAM1", "Banh Da Me 350gr", "goi", 350, source="test")
    customer_id = add_customer(conn, "Khach co hoa don", default_markup_pct=10)
    inv = create_invoice(conn, customer_id)
    add_line(conn, inv, "BADAM1", qty=1, markup_pct=10)
    finalize_invoice(conn, inv)

    with pytest.raises(ValueError):
        delete_customer(conn, customer_id)
    assert get_customer(conn, customer_id) is not None  # still there, untouched


def test_delete_customer_refuses_one_with_only_a_payment(conn):
    customer_id = add_customer(conn, "Khach co thanh toan")
    add_payment(conn, customer_id, 500, "2026-10-28")

    with pytest.raises(ValueError):
        delete_customer(conn, customer_id)
    assert get_customer(conn, customer_id) is not None
