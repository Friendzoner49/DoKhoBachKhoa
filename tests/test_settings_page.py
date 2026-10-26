"""Drives SettingsPage's actual button handlers, with every modal
dialog monkeypatched so this stays headless/non-blocking -- same spirit
as test_online_orders_ui.py. QApplication.instance().quit() is
monkeypatched too: the real one would tear down the shared qapp fixture
other tests still need."""
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from shop.core.customers import add_customer
from shop.core.invoices import add_line, create_invoice, finalize_invoice
from shop.core.products import upsert_product
from shop.core.transfer import export_package
from shop.db.migrate import connect
from shop.ui import settings_page as sp


class _FakeMainWindow:
    def __init__(self):
        self.refreshed = False

    def refresh_all_tabs(self):
        self.refreshed = True


class _FakeApp:
    def __init__(self):
        self.quit_called = False

    def quit(self):
        self.quit_called = True


def _silence_message_boxes(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))


def _seed(conn):
    upsert_product(conn, "BUN01", "Bún khô", "gói", 150, source="test")
    customer_id = add_customer(conn, "Khach test", default_markup_pct=10)
    invoice_id = create_invoice(conn, customer_id)
    add_line(conn, invoice_id, "BUN01", qty=2, markup_pct=10)
    finalize_invoice(conn, invoice_id)
    conn.commit()
    return customer_id


# ---- Khôi phục cài đặt gốc ----


def test_factory_reset_wipes_transactional_data_but_keeps_catalog(qapp, conn, monkeypatch):
    _silence_message_boxes(monkeypatch)
    monkeypatch.setattr(sp, "backup_now", lambda: None)
    monkeypatch.setattr(sp.TypedConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    _seed(conn)
    main_window = _FakeMainWindow()
    page = sp.SettingsPage(conn, main_window)

    page.factory_reset()

    assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert main_window.refreshed is True


def test_factory_reset_does_nothing_when_the_confirm_dialog_is_cancelled(qapp, conn, monkeypatch):
    _silence_message_boxes(monkeypatch)
    monkeypatch.setattr(sp, "backup_now", lambda: None)
    monkeypatch.setattr(sp.TypedConfirmDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    _seed(conn)
    main_window = _FakeMainWindow()
    page = sp.SettingsPage(conn, main_window)

    page.factory_reset()

    assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 1
    assert main_window.refreshed is False


# ---- Xuất dữ liệu ----


def test_export_data_writes_the_chosen_file(qapp, conn, monkeypatch, tmp_path):
    _silence_message_boxes(monkeypatch)
    monkeypatch.setattr("shop.ui.settings_page.supplier_invoices_dir", lambda: tmp_path / "photos")
    monkeypatch.setattr("shop.ui.settings_page.bot_sync_settings", lambda: ("", ""))
    dest = tmp_path / "chosen.shopdata"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(dest), "")))

    _seed(conn)
    page = sp.SettingsPage(conn, _FakeMainWindow())
    page.export_data()

    assert dest.exists()


def test_export_data_does_nothing_when_the_file_dialog_is_cancelled(qapp, conn, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    page = sp.SettingsPage(conn, _FakeMainWindow())
    page.export_data()  # must not raise


# ---- Nhập dữ liệu ----


def test_import_data_replaces_the_database_and_quits_the_app(qapp, conn, monkeypatch, tmp_path):
    _silence_message_boxes(monkeypatch)
    monkeypatch.setattr(sp, "backup_now", lambda: None)
    monkeypatch.setattr(sp.TypedConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    # The "incoming" package comes from a SEPARATE database (simulating
    # the other machine), never from the page's own `conn`.
    other_conn = connect(":memory:")
    upsert_product(other_conn, "BUN01", "Bún khô", "gói", 150, source="test")
    add_customer(other_conn, "Khach moi tu may kia")
    archive = export_package(other_conn, tmp_path / "incoming.shopdata", tmp_path / "incoming-photos")

    dest_db = tmp_path / "live" / "shop.sqlite"
    dest_db.parent.mkdir(parents=True)
    seed_conn = connect(dest_db)
    add_customer(seed_conn, "Khach cu tren may nay")
    seed_conn.close()
    dest_photos = tmp_path / "live" / "supplier_invoices"

    monkeypatch.setattr("shop.ui.settings_page.db_path", lambda: dest_db)
    monkeypatch.setattr("shop.ui.settings_page.supplier_invoices_dir", lambda: dest_photos)
    monkeypatch.setattr("shop.ui.settings_page.bot_sync_settings", lambda: ("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(archive), "")))
    fake_app = _FakeApp()
    monkeypatch.setattr(sp.QApplication, "instance", staticmethod(lambda: fake_app))

    page = sp.SettingsPage(conn, _FakeMainWindow())
    page.import_data()

    assert fake_app.quit_called is True
    reopened = connect(dest_db)
    try:
        names = [row[0] for row in reopened.execute("SELECT name FROM customers").fetchall()]
        assert names == ["Khach moi tu may kia"]  # old data replaced, not merged
    finally:
        reopened.close()


def test_import_data_does_nothing_when_the_confirm_dialog_is_cancelled(qapp, conn, monkeypatch, tmp_path):
    _silence_message_boxes(monkeypatch)
    monkeypatch.setattr(sp.TypedConfirmDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    other_conn = connect(":memory:")
    add_customer(other_conn, "Khach moi")
    archive = export_package(other_conn, tmp_path / "incoming.shopdata", tmp_path / "photos")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(archive), "")))
    fake_app = _FakeApp()
    monkeypatch.setattr(sp.QApplication, "instance", staticmethod(lambda: fake_app))

    _seed(conn)
    page = sp.SettingsPage(conn, _FakeMainWindow())
    page.import_data()

    assert fake_app.quit_called is False
    assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 1  # untouched


def test_import_data_rejects_a_newer_schema_and_never_closes_the_connection(qapp, conn, monkeypatch, tmp_path):
    _silence_message_boxes(monkeypatch)
    bad = tmp_path / "future.shopdata"
    import json
    import zipfile

    with zipfile.ZipFile(bad, "w") as z:
        z.writestr(
            "manifest.json",
            json.dumps({"exported_at": "x", "schema_version": 999999, "products": 0, "customers": 0, "invoices": 0}),
        )
        z.writestr("shop.sqlite", b"unused")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad), "")))

    page = sp.SettingsPage(conn, _FakeMainWindow())
    page.import_data()

    # Rejected before the typed-confirm step even appears -- conn must
    # still be open and usable.
    assert conn.execute("SELECT 1").fetchone() == (1,)
