"""Drives ProductsPage's actual button/checkbox handlers (not just
shop.core.products.set_active, which other tests already cover) -- same
reasoning as test_supplier_invoices_ui.py for its sibling dialogs."""
from PySide6.QtWidgets import QMessageBox

from shop.core.products import get_product, upsert_product
from shop.ui.dialogs import ProductDialog
from shop.ui.products_page import ProductsPage


def _seed(conn, code="RUOU01", name="Rượu Tết 2026", active=True):
    upsert_product(conn, code, name, "chai", 100, active=active, source="test")


def test_hidden_products_are_excluded_from_the_list_by_default(qapp, conn):
    _seed(conn, "A1", active=True)
    _seed(conn, "A2", active=False)
    page = ProductsPage(conn)
    codes = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert codes == {"A1"}


def test_checking_show_hidden_reveals_inactive_products(qapp, conn):
    _seed(conn, "A1", active=True)
    _seed(conn, "A2", active=False)
    page = ProductsPage(conn)
    page.show_hidden_check.setChecked(True)
    codes = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert codes == {"A1", "A2"}


def test_status_combo_shows_the_selected_rows_current_status(qapp, conn):
    _seed(conn, "A1", name="Mat hang dang ban", active=True)  # "Đang bán"
    upsert_product(conn, "A2", "Mat hang tam het", "kg", 100, active=True, source="test")
    from shop.core.products import set_in_stock

    set_in_stock(conn, "A2", False)  # "Tạm hết hàng"
    page = ProductsPage(conn)

    def _row_for(code):
        for row in range(page.table.rowCount()):
            if page.table.item(row, 0).text() == code:
                return row
        raise AssertionError(f"code {code} not found in table")

    page.table.selectRow(_row_for("A1"))
    assert page.status_combo.currentText() == "Đang bán"
    page.table.selectRow(_row_for("A2"))
    assert page.status_combo.currentText() == "Tạm hết hàng"


def test_apply_status_ngung_ban_hides_the_product_after_confirming(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    _seed(conn, "RUOU01", active=True)
    page = ProductsPage(conn)
    page.table.selectRow(0)
    page.status_combo.setCurrentText("Ngừng bán")

    page.apply_status()

    assert page.table.rowCount() == 0  # hidden from the default (active-only) view
    page.show_hidden_check.setChecked(True)
    assert page.table.rowCount() == 1
    assert page.table.item(0, 7).text() == "Ngừng bán"


def test_apply_status_ngung_ban_does_nothing_if_the_owner_declines(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    _seed(conn, "RUOU01", active=True)
    page = ProductsPage(conn)
    page.table.selectRow(0)
    page.status_combo.setCurrentText("Ngừng bán")

    page.apply_status()

    assert page.table.rowCount() == 1  # still active, still shown
    assert page.status_combo.currentText() == "Đang bán"  # reverted, not left stuck on the declined choice


def test_apply_status_tam_het_hang_does_not_affect_active(qapp, conn):
    _seed(conn, "A1", active=True)
    page = ProductsPage(conn)
    page.table.selectRow(0)
    page.status_combo.setCurrentText("Tạm hết hàng")

    page.apply_status()

    assert page.table.item(0, 7).text() == "Tạm hết hàng"
    page.table.selectRow(0)
    assert page.status_combo.currentText() == "Tạm hết hàng"

    # And back to "Đang bán" reactivates stock without touching active.
    page.status_combo.setCurrentText("Đang bán")
    page.apply_status()
    assert page.table.item(0, 7).text() == "Còn hàng"


def test_double_clicking_a_row_opens_the_edit_dialog_with_name_ru_field(qapp, conn, monkeypatch):
    """Request 03/11/2026: check tên tiếng Nga against a supplier invoice
    photo before next week's delivery -- double-clicking any row must open
    the same detail/edit dialog "Sửa" uses, already showing the field."""
    _seed(conn, "A1", active=True)

    def _accept_and_fill_name_ru(self):
        assert self.name_ru_edit.text() == ""  # defaults blank until filled in via orders
        self.name_ru_edit.setText("Рис Жасмин")
        return True

    monkeypatch.setattr(ProductDialog, "exec", _accept_and_fill_name_ru)

    page = ProductsPage(conn)
    page.table.selectRow(0)
    page.table.itemDoubleClicked.emit(page.table.item(0, 0))

    assert get_product(conn, "A1")["name_ru"] == "Рис Жасмин"
