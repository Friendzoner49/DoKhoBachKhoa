"""Drives SupplierInvoicesPage's actual sync button handler (not just
shop.core.supplier_invoices.sync_photos_from_bot, which
test_supplier_invoices.py already covers) -- same reasoning as
test_online_orders_ui.py for its sibling sync button."""
import base64
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QMessageBox

from shop.core.products import upsert_product
from shop.core.supplier_invoices import add_line, create_invoice
from shop.ocr.vision import VisionOcrUnavailable
from shop.ui import supplier_invoices_page as sip
from shop.ui.supplier_invoice_dialog import SupplierInvoiceDialog, _KnownLinesPickerDialog


class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_sync_photos_now_creates_a_draft_invoice_visible_in_the_table(qapp, conn, monkeypatch, tmp_path):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr("shop.ui.supplier_invoices_page.bot_sync_settings", lambda: ("https://example.test", "secret"))
    monkeypatch.setattr("shop.ui.supplier_invoices_page.supplier_invoices_dir", lambda: tmp_path)

    payload = {
        "photos": [
            {
                "key": "photo:0001-aa",
                "note": "hàng về đợt 25/10",
                "data": base64.b64encode(b"\xff\xd8\xff fake jpeg").decode("ascii"),
            }
        ]
    }
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(payload))

    page = sip.SupplierInvoicesPage(conn)
    page.sync_photos_now()

    assert page.table.rowCount() == 1
    assert page.table.item(0, 3).text() == "hàng về đợt 25/10"  # col 3 = "Ghi chú"
    assert (tmp_path / "1-telegram.jpg").exists()


def _accept_picker_with_all_rows_checked(self):
    """Stands in for the owner ticking every row in the checklist and
    accepting it -- used to drive add_known_lines() without a real
    modal event loop, same pattern as other *_ui.py tests monkeypatch
    a dialog's exec() (see test_settings_page.py)."""
    for row in range(self.table.rowCount()):
        self.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
    return QDialog.DialogCode.Accepted


def test_add_known_lines_lets_the_owner_tick_which_items_apply_to_this_invoice(qapp, conn, monkeypatch):
    """lần 22: real OCR testing on actual photographed invoices showed
    Tesseract cannot reliably read the item TABLE (only the header) --
    so instead of OCR auto-fill, "Thêm mặt hàng quen thuộc" opens a
    checklist built from the owner's own past confirmed matches, and
    only the TICKED ones get added (never a blind bulk-insert -- with
    only one supplier that would grow toward the whole catalog)."""
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(_KnownLinesPickerDialog, "exec", _accept_picker_with_all_rows_checked)
    upsert_product(conn, "BUN01", "Bún Tươi Thanh Loc", "gói", 150, source="test")

    old_invoice = create_invoice(conn)
    add_line(
        conn, old_invoice,
        raw_name="Bun Tuoi Ha Noi THANH LOC 500g", raw_qty=3, raw_unit="шт",
        raw_unit_price=150, matched_code="BUN01", unit_conversion=1.0,
    )

    dialog = SupplierInvoiceDialog(None, conn)  # invoice_id=None -> brand new draft
    dialog.add_known_lines()

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "Bun Tuoi Ha Noi THANH LOC 500g"
    assert dialog.table.item(0, 1).text() == "3"  # SL column, carried over as a starting default
    assert dialog.table.item(0, 3).text() == ""  # Đơn giá left blank on purpose
    assert dialog.table.item(0, 5).text() == "BUN01"  # Mã hàng khớp column

    # Clicking again must not duplicate the row for a code already present
    # (already-on-invoice codes aren't even offered in the picker).
    dialog.add_known_lines()
    assert dialog.table.rowCount() == 1


def test_add_known_lines_only_adds_rows_the_owner_actually_ticked(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    def _accept_with_nothing_checked(self):
        return QDialog.DialogCode.Accepted  # no rows ticked

    monkeypatch.setattr(_KnownLinesPickerDialog, "exec", _accept_with_nothing_checked)
    upsert_product(conn, "BUN01", "Bún Tươi Thanh Loc", "gói", 150, source="test")
    old_invoice = create_invoice(conn)
    add_line(
        conn, old_invoice,
        raw_name="Bun Tuoi", raw_qty=3, raw_unit="шт", raw_unit_price=150, matched_code="BUN01",
    )

    dialog = SupplierInvoiceDialog(None, conn)
    dialog.add_known_lines()

    assert dialog.table.rowCount() == 0


def _dialog_with_a_photo(conn, tmp_path):
    dialog = SupplierInvoiceDialog(None, conn)
    image_path = tmp_path / "invoice.png"
    QPixmap(10, 10).save(str(image_path))
    dialog._image_path = image_path
    return dialog


def test_run_vision_ocr_shows_the_models_text_and_restores_the_cursor(qapp, conn, monkeypatch, tmp_path):
    dialog = _dialog_with_a_photo(conn, tmp_path)
    monkeypatch.setattr(
        "shop.ui.supplier_invoice_dialog.read_invoice_table",
        lambda path, **k: "1. Nuoc mam CHINSU 250ml, 2, chai, 150.00, 300.00",
    )

    dialog.run_vision_ocr()

    assert "Nuoc mam" in dialog.ocr_text.toPlainText()
    from PySide6.QtWidgets import QApplication

    assert QApplication.overrideCursor() is None  # restored, not stuck in WaitCursor


def test_run_vision_ocr_shows_the_vietnamese_error_when_ollama_is_unavailable(qapp, conn, monkeypatch, tmp_path):
    dialog = _dialog_with_a_photo(conn, tmp_path)

    def _raise(path, **k):
        raise VisionOcrUnavailable("Chưa chạy Ollama trên máy này.")

    monkeypatch.setattr("shop.ui.supplier_invoice_dialog.read_invoice_table", _raise)

    dialog.run_vision_ocr()

    assert "Chưa chạy Ollama" in dialog.ocr_text.toPlainText()
    from PySide6.QtWidgets import QApplication

    assert QApplication.overrideCursor() is None
