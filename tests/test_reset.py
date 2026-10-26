from shop.core.customers import add_customer
from shop.core.invoices import add_line, create_invoice, finalize_invoice
from shop.core.online_orders import close_batch, link_customer
from shop.core.payments import add_payment
from shop.core.products import upsert_product
from shop.core.reset import reset_transactional_data, transactional_counts
from shop.core.supplier_invoices import add_line as add_supplier_line
from shop.core.supplier_invoices import create_invoice as create_supplier_invoice


def _seed_everything(conn):
    upsert_product(conn, "BUN01", "Bún khô", "gói", 150, source="test")
    customer_id = add_customer(conn, "Khach test", default_markup_pct=10)
    invoice_id = create_invoice(conn, customer_id)
    add_line(conn, invoice_id, "BUN01", qty=2, markup_pct=10)
    finalize_invoice(conn, invoice_id)
    add_payment(conn, customer_id, 100)

    si_id = create_supplier_invoice(conn, invoice_number="TEST-1")
    add_supplier_line(conn, si_id, raw_name="Bun kho", raw_qty=1, raw_unit="goi", raw_unit_price=150, matched_code="BUN01")

    conn.execute(
        """
        INSERT INTO online_orders
            (source_key, telegram_chat_id, customer_label, customer_phone, total_estimated, status, placed_at, synced_at)
        VALUES ('sync:0001-1-aa', '1', 'Khach online', NULL, 322, 'cho_xu_ly', '2026-10-19T00:00:00', '2026-10-19T00:00:00')
        """
    )
    online_order_id = conn.execute("SELECT id FROM online_orders").fetchone()[0]
    conn.execute(
        "INSERT INTO online_order_lines (online_order_id, code, qty, name_at_order, price_at_order) VALUES (?, 'BUN01', 2, 'Bún khô', 161)",
        (online_order_id,),
    )
    link_customer(conn, "1", customer_id)
    close_batch(conn)
    conn.commit()
    return customer_id


def test_transactional_counts_reports_everything_a_reset_would_delete(conn):
    _seed_everything(conn)
    counts = transactional_counts(conn)
    assert counts == {
        "customers": 1,
        "invoices": 1,
        "payments": 1,
        "supplier_invoices": 1,
        "online_orders": 1,
    }


def test_reset_wipes_every_transactional_table(conn):
    _seed_everything(conn)
    reset_transactional_data(conn)

    for table in ("customers", "invoices", "invoice_lines", "payments", "supplier_invoices", "supplier_invoice_lines", "online_orders", "online_order_lines", "telegram_customer_links", "order_batches"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count == 0, f"expected {table} to be empty after reset, found {count} row(s)"


def test_reset_keeps_the_product_catalog_and_supplier_aliases(conn):
    customer_id = _seed_everything(conn)
    conn.execute(
        "INSERT INTO supplier_aliases (raw_name_normalized, product_code, unit_conversion) VALUES ('bun kho', 'BUN01', 1)"
    )
    conn.commit()

    reset_transactional_data(conn)

    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert conn.execute("SELECT code FROM products").fetchone()[0] == "BUN01"
    assert conn.execute("SELECT COUNT(*) FROM supplier_aliases").fetchone()[0] == 1

    # And a fresh customer added right after starts back at id 1 --
    # autoincrement was actually cleared, not left stuck past the wiped
    # data's old ids.
    new_id = add_customer(conn, "Khach moi")
    assert new_id == 1 == customer_id


def test_reset_is_safe_to_run_on_an_already_empty_database(conn):
    transactional_counts(conn)  # must not raise even with nothing seeded
    reset_transactional_data(conn)  # must not raise either
