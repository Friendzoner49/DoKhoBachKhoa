"""Draft invoice lines are editable in the dialog (name, unit, qty, cost,
price) and a negative custom line works as a discount."""
from shop.core.invoices import add_custom_line, get_invoice
from shop.ui.invoice_editor import COL_NAME, COL_PRICE, COL_UNIT, InvoiceEditorDialog
from shop.core.customers import add_customer
from shop.core.invoices import add_line, create_invoice, finalize_invoice
from shop.core.products import upsert_product


def _seed_invoice(conn, status="draft"):
    upsert_product(conn, "BADAM1", "Banh Da Me 350gr", "goi", 350, source="test")
    invoice_id = create_invoice(conn, add_customer(conn, "Chi test", default_markup_pct=10))
    add_line(conn, invoice_id, "BADAM1", qty=1, markup_pct=10)
    if status == "finalized":
        finalize_invoice(conn, invoice_id)
    return invoice_id


def test_draft_name_unit_price_cells_editable_and_saved(qapp, conn):
    invoice_id = _seed_invoice(conn, "draft")
    dialog = InvoiceEditorDialog(None, conn, invoice_id)
    from PySide6.QtCore import Qt

    for col in (COL_NAME, COL_UNIT, COL_PRICE):
        assert dialog.table.item(0, col).flags() & Qt.ItemFlag.ItemIsEditable

    dialog.table.item(0, COL_NAME).setText("Bánh đa mè tặng kèm")
    dialog.table.item(0, COL_UNIT).setText("túi")
    dialog.table.item(0, COL_PRICE).setText("300")

    line = get_invoice(conn, invoice_id)["lines"][0]
    assert line["product_name_snapshot"] == "Bánh đa mè tặng kèm"
    assert line["unit_snapshot"] == "túi"
    assert line["unit_price"] == 300
    assert line["line_total"] == 300


def test_negative_custom_line_is_a_discount(qapp, conn):
    invoice_id = _seed_invoice(conn, "draft")
    before = get_invoice(conn, invoice_id)["total"]
    add_custom_line(conn, invoice_id, "Giảm giá khách quen", unit_price=-50, qty=1)
    assert get_invoice(conn, invoice_id)["total"] == before - 50


def test_finalized_cells_not_editable(qapp, conn):
    from PySide6.QtCore import Qt

    dialog = InvoiceEditorDialog(None, conn, _seed_invoice(conn, "finalized"))
    assert not dialog.table.item(0, COL_NAME).flags() & Qt.ItemFlag.ItemIsEditable
