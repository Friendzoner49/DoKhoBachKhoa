"""Smoke test: build every page and drive customer -> invoice -> finalize
-> export without a real display (QT_QPA_PLATFORM=offscreen, set in
conftest.py). This only proves the widgets construct and the plumbing
between shop.core and shop.ui doesn't crash — it is not a substitute for
actually looking at the app."""
from shop.core.customers import add_customer
from shop.core.invoices import add_line, create_invoice, finalize_invoice
from shop.core.products import upsert_product
from shop.excel.catalog_export import export_catalog
from shop.excel.invoice_export import export_invoice
from shop.excel.summary_export import export_summary
from shop.ui.invoice_editor import InvoiceEditorDialog
from shop.ui.main_window import MainWindow


def test_full_ui_flow_offscreen(qapp, tmp_path):
    from shop.db.migrate import connect

    conn = connect(tmp_path / "smoke.sqlite")
    upsert_product(conn, "BADAM1", "Banh Da Me 350gr", "goi", 350, source="test")
    customer_id = add_customer(conn, "Chi Test", default_markup_pct=10)

    window = MainWindow(conn)
    assert window.products_page.table.rowCount() == 1
    assert window.customers_page.table.rowCount() == 1

    invoice_id = create_invoice(conn, customer_id)
    add_line(conn, invoice_id, "BADAM1", qty=2, markup_pct=10)

    editor = InvoiceEditorDialog(window, conn, invoice_id)
    assert editor.table.rowCount() == 1
    assert editor.is_draft
    # Call the core function directly, not editor.finalize(), which pops a
    # confirmation QMessageBox that would block this headless test.
    finalize_invoice(conn, invoice_id)
    editor.refresh()
    assert not editor.is_draft

    window.invoices_page.refresh()
    assert window.invoices_page.table.rowCount() == 1

    window.summary_page.refresh()
    assert window.summary_page.table.rowCount() == 1

    window.online_orders_page.refresh()
    assert window.online_orders_page.table.rowCount() == 0

    window.settings_page.refresh()

    export_catalog(conn, tmp_path / "catalog.xlsx")
    export_invoice(conn, invoice_id, tmp_path / "invoice.xlsx")
    export_summary(conn, tmp_path / "summary.xlsx")
    assert (tmp_path / "catalog.xlsx").exists()
    assert (tmp_path / "invoice.xlsx").exists()
    assert (tmp_path / "summary.xlsx").exists()
