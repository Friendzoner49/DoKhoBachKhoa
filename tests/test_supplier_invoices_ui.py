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
from shop.core.supplier_invoices import add_line, create_invoice, get_invoice
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
        "shop.ui.supplier_invoice_dialog.read_invoice_rows",
        lambda path, **k: [
            {"name_ru": "Рыбный соус CHINSU 250мл", "name_latin": "Nuoc mam CHINSU 250ml",
             "qty": 2, "unit": "chai", "unit_price": 150.0, "line_total": 300.0}
        ],
    )

    dialog.run_vision_ocr()

    assert "Nuoc mam" in dialog.ocr_text.toPlainText()
    assert dialog.insert_vision_btn.isEnabled()
    from PySide6.QtWidgets import QApplication

    assert QApplication.overrideCursor() is None  # restored, not stuck in WaitCursor


def test_run_vision_ocr_shows_the_vietnamese_error_when_ollama_is_unavailable(qapp, conn, monkeypatch, tmp_path):
    dialog = _dialog_with_a_photo(conn, tmp_path)

    def _raise(path, **k):
        raise VisionOcrUnavailable("Chưa chạy Ollama trên máy này.")

    monkeypatch.setattr("shop.ui.supplier_invoice_dialog.read_invoice_rows", _raise)

    dialog.run_vision_ocr()

    assert "Chưa chạy Ollama" in dialog.ocr_text.toPlainText()
    assert not dialog.insert_vision_btn.isEnabled()
    from PySide6.QtWidgets import QApplication

    assert QApplication.overrideCursor() is None


def test_insert_vision_rows_adds_a_draft_line_with_russian_name_and_prefills_known_alias(qapp, conn, monkeypatch, tmp_path):
    from shop.core.products import upsert_product
    from shop.core.supplier_invoices import save_alias

    upsert_product(conn, "MAM001", "Nước Mắm Chinsu 250ml", "chai", 140, source="test")
    save_alias(conn, "Nuoc mam CHINSU 250ml", "MAM001", 1.0)

    dialog = _dialog_with_a_photo(conn, tmp_path)
    dialog._vision_rows = [
        {"name_ru": "Рыбный соус CHINSU 250мл", "name_latin": "Nuoc mam CHINSU 250ml",
         "qty": 2.0, "unit": "chai", "unit_price": 150.0, "line_total": 300.0}
    ]
    dialog.insert_vision_btn.setEnabled(True)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    dialog.insert_vision_rows()

    lines = get_invoice(conn, dialog.invoice_id)["lines"]
    assert len(lines) == 1
    assert lines[0]["raw_name"] == "Nuoc mam CHINSU 250ml"
    assert lines[0]["raw_name_ru"] == "Рыбный соус CHINSU 250мл"
    assert lines[0]["matched_code"] == "MAM001"  # pre-filled from the EXACT saved alias
    assert not dialog._vision_rows
    assert not dialog.insert_vision_btn.isEnabled()


def test_suggest_with_no_close_match_opens_the_name_code_search(qapp, conn, monkeypatch):
    upsert_product(conn, "BUN01", "Bún Tươi Thanh Loc", "gói", 150, source="test")
    invoice_id = create_invoice(conn)
    add_line(conn, invoice_id, raw_name="Zzzz qqq", raw_qty=1, raw_unit="шт", raw_unit_price=150)
    dialog = SupplierInvoiceDialog(None, conn, invoice_id)
    dialog.table.setCurrentCell(0, 0)

    opened = []

    def _pick_bun(self):
        opened.append(type(self).__name__)
        self.selected_code = "BUN01"
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("shop.ui.supplier_invoice_dialog.ProductPickerDialog.exec", _pick_bun)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: opened.append("msgbox")))
    dialog.suggest_for_selected()

    assert opened == ["ProductPickerDialog"]
    assert get_invoice(conn, invoice_id)["lines"][0]["matched_code"] == "BUN01"


def test_product_picker_search_ignores_vietnamese_accents(qapp):
    from shop.ui.dialogs import ProductPickerDialog

    products = [
        {"code": "MONHI1", "name": "Mọc Nhĩ", "cost_price": 150},
        {"code": "VUTRA1", "name": "Vừng Trắng", "cost_price": 50},
    ]
    picker = ProductPickerDialog(None, products)
    for query in ("mộc nhĩ", "moc nhi", "MỌC"):
        picker.search_edit.setText(query)
        assert [picker.list_widget.item(i).data(256) for i in range(picker.list_widget.count())] == ["MONHI1"], query


def test_opening_a_blank_draft_fills_next_number_and_today(qapp, conn):
    from datetime import date

    applied = create_invoice(conn, invoice_number="7", invoice_date="2026-11-01")
    conn.execute("UPDATE supplier_invoices SET applied_at = '2026-11-01' WHERE id = ?", (applied,))
    draft = create_invoice(conn)  # e.g. pulled in from Telegram: no number, no date
    dialog = SupplierInvoiceDialog(None, conn, draft)
    assert dialog.number_edit.text() == "8"
    assert dialog.date_edit.text() == date.today().isoformat()
    saved = get_invoice(conn, draft)
    assert (saved["invoice_number"], saved["invoice_date"]) == ("8", date.today().isoformat())

    # an applied invoice is never renumbered
    conn.execute("UPDATE supplier_invoices SET invoice_number = NULL WHERE id = ?", (applied,))
    SupplierInvoiceDialog(None, conn, applied)
    assert get_invoice(conn, applied)["invoice_number"] is None
