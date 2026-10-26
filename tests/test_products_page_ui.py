"""Drives ProductsPage's actual button/checkbox handlers (not just
shop.core.products.set_active, which other tests already cover) -- same
reasoning as test_supplier_invoices_ui.py for its sibling dialogs."""
from PySide6.QtWidgets import QMessageBox

from shop.core.products import upsert_product
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


def test_delete_from_catalog_hides_the_product_after_confirming(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    _seed(conn, "RUOU01", active=True)
    page = ProductsPage(conn)
    page.table.selectRow(0)

    page.delete_from_catalog()

    assert page.table.rowCount() == 0  # hidden from the default (active-only) view
    page.show_hidden_check.setChecked(True)
    assert page.table.rowCount() == 1
    assert page.table.item(0, 7).text() == "Ngừng bán"


def test_delete_from_catalog_does_nothing_if_the_owner_declines(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    _seed(conn, "RUOU01", active=True)
    page = ProductsPage(conn)
    page.table.selectRow(0)

    page.delete_from_catalog()

    assert page.table.rowCount() == 1  # still active, still shown


def test_delete_from_catalog_on_an_already_hidden_product_just_informs(qapp, conn, monkeypatch):
    informed = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: informed.append(a)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    _seed(conn, "RUOU01", active=False)
    page = ProductsPage(conn)
    page.show_hidden_check.setChecked(True)
    page.table.selectRow(0)

    page.delete_from_catalog()

    assert len(informed) == 1
