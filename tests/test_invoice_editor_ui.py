"""Drives InvoiceEditorDialog's actual "🗑 Xóa hóa đơn" button handler
(not just shop.core.invoices.delete_invoice, which test_invoices.py
already covers) -- same reasoning as test_products_page_ui.py."""
from PySide6.QtWidgets import QMessageBox

from shop.core.customers import add_customer
from shop.core.invoices import add_line, cancel_invoice, create_invoice, finalize_invoice, get_invoice
from shop.core.products import upsert_product
from shop.ui.invoice_editor import InvoiceEditorDialog


def _seed_invoice(conn, status="draft"):
    upsert_product(conn, "BADAM1", "Banh Da Me 350gr", "goi", 350, source="test")
    customer_id = add_customer(conn, "Chi test", default_markup_pct=10)
    invoice_id = create_invoice(conn, customer_id)
    add_line(conn, invoice_id, "BADAM1", qty=1, markup_pct=10)
    if status == "finalized":
        finalize_invoice(conn, invoice_id)
    elif status == "cancelled":
        finalize_invoice(conn, invoice_id)
        cancel_invoice(conn, invoice_id)
    return invoice_id


def test_delete_button_enabled_for_draft_and_cancelled_not_finalized(qapp, conn):
    draft_id = _seed_invoice(conn, "draft")
    assert InvoiceEditorDialog(None, conn, draft_id).delete_btn.isEnabled()

    finalized_id = _seed_invoice(conn, "finalized")
    assert not InvoiceEditorDialog(None, conn, finalized_id).delete_btn.isEnabled()

    cancelled_id = _seed_invoice(conn, "cancelled")
    assert InvoiceEditorDialog(None, conn, cancelled_id).delete_btn.isEnabled()


def test_delete_invoice_dialog_removes_a_non_empty_draft_after_confirming(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    invoice_id = _seed_invoice(conn, "draft")
    dialog = InvoiceEditorDialog(None, conn, invoice_id)

    dialog.delete_invoice_dialog()

    assert get_invoice(conn, invoice_id) is None


def test_delete_invoice_dialog_does_nothing_if_the_owner_declines(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    invoice_id = _seed_invoice(conn, "draft")
    dialog = InvoiceEditorDialog(None, conn, invoice_id)

    dialog.delete_invoice_dialog()

    assert get_invoice(conn, invoice_id) is not None
