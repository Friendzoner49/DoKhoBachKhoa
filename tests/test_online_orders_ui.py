"""Drives OnlineOrdersPage's actual button handlers (not just the
shop.core functions test_online_orders.py already covers), with the
modal dialogs monkeypatched so this stays headless/non-blocking --
same spirit as test_ui_smoke.py calling finalize_invoice() directly
instead of clicking through InvoiceEditorDialog's own confirmation."""
import json

from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from shop.core import supplier_invoices as supplier_invoices_core
from shop.core.customers import add_customer
from shop.core.online_orders import linked_customer_id, list_online_orders
from shop.core.products import upsert_product
from shop.ui import online_orders_page as oop


class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _seed_online_order(conn, monkeypatch):
    upsert_product(conn, "BUN01", "Bún khô", "goi", 150, source="test")
    payload = {
        "orders": [
            {
                "key": "sync:0001-111-ab",
                "telegram_chat_id": 111,
                "customer_label": "Khach Test",
                "customer_phone": "+79990001122",
                "total_estimated": 322,
                "created_at": "2026-10-19T10:00:00Z",
                "lines": [{"code": "BUN01", "qty": 2, "name": "Bún khô", "price": 161}],
            }
        ]
    }
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(payload))


def test_convert_selected_creates_an_invoice_and_links_the_customer(qapp, conn, monkeypatch):
    # QMessageBox.information/.question/.warning would otherwise pop a
    # REAL modal event loop even under QT_QPA_PLATFORM=offscreen and
    # block forever with nobody to click OK -- same reason
    # test_ui_smoke.py avoids editor.finalize() in favor of calling the
    # core function directly.
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    _seed_online_order(conn, monkeypatch)
    customer_id = add_customer(conn, "Khach Test")

    page = oop.OnlineOrdersPage(conn)
    worker_url, sync_secret = "https://example.test", "secret"
    monkeypatch.setattr("shop.ui.online_orders_page.bot_sync_settings", lambda: (worker_url, sync_secret))
    page.sync_now()
    assert page.table.rowCount() == 1

    page.table.selectRow(0)
    monkeypatch.setattr(page, "_pick_customer", lambda customers, order: customer_id)
    monkeypatch.setattr(oop.InvoiceEditorDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    page.convert_selected()

    assert linked_customer_id(conn, "111") == customer_id
    page.refresh()
    assert page.table.item(0, 7).text() == "Đã tạo hóa đơn"  # col 7 = Trạng thái, after "Đợt" was inserted at col 1


def test_convert_selected_reuses_the_previously_linked_customer_without_asking_again(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    _seed_online_order(conn, monkeypatch)
    customer_id = add_customer(conn, "Khach cu")

    page = oop.OnlineOrdersPage(conn)
    monkeypatch.setattr("shop.ui.online_orders_page.bot_sync_settings", lambda: ("https://example.test", "secret"))
    page.sync_now()
    page.table.selectRow(0)
    monkeypatch.setattr(page, "_pick_customer", lambda customers, order: customer_id)
    monkeypatch.setattr(oop.InvoiceEditorDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    page.convert_selected()  # first order: links chat 111 -> customer_id

    # A second order from the SAME Telegram chat should offer to reuse
    # the link instead of asking to pick a customer again.
    payload = {
        "orders": [
            {
                "key": "sync:0002-111-cd",
                "telegram_chat_id": 111,
                "customer_label": "Khach Test",
                "customer_phone": "+79990001122",
                "total_estimated": 161,
                "created_at": "2026-10-19T11:00:00Z",
                "lines": [{"code": "BUN01", "qty": 1, "name": "Bún khô", "price": 161}],
            }
        ]
    }
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(payload))
    page.sync_now()

    picked_without_asking = []
    monkeypatch.setattr(page, "_pick_customer", lambda customers, order: picked_without_asking.append(1) or customer_id)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    pending_row = next(i for i in range(page.table.rowCount()) if page._orders[i]["status"] == "cho_xu_ly")
    page.table.selectRow(pending_row)
    page.convert_selected()

    assert picked_without_asking == []  # reused the link, never fell through to the picker


def test_close_batch_then_exclude_and_restore_an_item_through_the_review_dialog(qapp, conn, monkeypatch):
    """Drives the actual button handlers for request #1/#2 (lần 19), not
    just the shop.core functions test_online_orders.py already covers --
    same reasoning as the rest of this file."""
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    upsert_product(conn, "BUN01", "Bún khô", "gói", 150, source="test")
    payload = {
        "orders": [
            {
                "key": "sync:0001-111-ab",
                "telegram_chat_id": 111,
                "customer_label": "Khach A",
                "customer_phone": None,
                "total_estimated": 161,
                "created_at": "2026-10-19T10:00:00Z",
                "lines": [{"code": "BUN01", "qty": 1, "name": "Bún khô", "price": 161}],
            }
        ]
    }
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(payload))

    page = oop.OnlineOrdersPage(conn)
    monkeypatch.setattr("shop.ui.online_orders_page.bot_sync_settings", lambda: ("https://example.test", "secret"))
    page.close_batch_now()  # syncs, then closes a batch with that 1 order
    page.refresh()
    assert page.table.item(0, 1).text() == "Đợt #1"

    batches = oop.list_batches(conn)
    review = oop.BatchReviewDialog(page, conn, batches[0]["id"])
    assert review._demand == [{"code": "BUN01", "name": "Bún khô", "total_qty": 1, "order_count": 1}]

    review.demand_table.selectRow(0)
    review._exclude_selected()
    assert review._demand == []
    assert review._excluded == [{"code": "BUN01", "name": "Bún khô", "order_count": 1}]

    review.excluded_table.selectRow(0)
    review._restore_selected()
    assert review._demand == [{"code": "BUN01", "name": "Bún khô", "total_qty": 1, "order_count": 1}]
    assert review._excluded == []


def _closed_batch_with_one_order(conn, monkeypatch, qty=1, price=161):
    upsert_product(conn, "BUN01", "Bún khô", "gói", 150, source="test")
    payload = {
        "orders": [
            {
                "key": "sync:0001-111-ab",
                "telegram_chat_id": 111,
                "customer_label": "Khach A",
                "customer_phone": None,
                "total_estimated": qty * price,
                "created_at": "2026-10-19T10:00:00Z",
                "lines": [{"code": "BUN01", "qty": qty, "name": "Bún khô", "price": price}],
            }
        ]
    }
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(payload))
    page = oop.OnlineOrdersPage(conn)
    monkeypatch.setattr("shop.ui.online_orders_page.bot_sync_settings", lambda: ("https://example.test", "secret"))
    page.close_batch_now()
    batch_id = oop.list_batches(conn)[0]["id"]
    return page, batch_id


def test_link_invoice_through_the_review_dialog_picker(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    page, batch_id = _closed_batch_with_one_order(conn, monkeypatch)
    inv_id = supplier_invoices_core.create_invoice(conn, invoice_number="UT-1")

    review = oop.BatchReviewDialog(page, conn, batch_id)
    assert review.invoices_list.count() == 0

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: (a[3][0], True)))
    review._link_invoice()

    assert review.invoices_list.count() == 1
    assert review.invoices_list.item(0).data(oop.Qt.ItemDataRole.UserRole) == inv_id

    review.invoices_list.setCurrentRow(0)
    review._unlink_invoice()
    assert review.invoices_list.count() == 0


def test_check_and_notify_blocks_when_the_linked_invoice_has_unmatched_lines(qapp, conn, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a)))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    page, batch_id = _closed_batch_with_one_order(conn, monkeypatch)
    inv_id = supplier_invoices_core.create_invoice(conn)
    supplier_invoices_core.add_line(conn, inv_id, "chua khop", 1, "шт", 100, matched_code=None)
    oop.link_invoice_to_batch(conn, inv_id, batch_id)

    review = oop.BatchReviewDialog(page, conn, batch_id)
    review._check_and_notify()

    assert len(warned) == 1  # refused to proceed, no crash


def test_check_and_notify_sends_directly_when_everything_matches_exactly(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    page, batch_id = _closed_batch_with_one_order(conn, monkeypatch, qty=2)
    inv_id = supplier_invoices_core.create_invoice(conn)
    supplier_invoices_core.add_line(conn, inv_id, "Bun kho", 2, "шт", 150, matched_code="BUN01", unit_conversion=1)
    oop.link_invoice_to_batch(conn, inv_id, batch_id)

    sent_payloads = []
    monkeypatch.setattr(
        "shop.ui.online_orders_page.send_arrival_notifications",
        lambda conn, batch_id, url, secret: sent_payloads.append((batch_id,)) or {"sent": [{"online_order_id": 1}], "failed": []},
    )
    review = oop.BatchReviewDialog(page, conn, batch_id)

    review._check_and_notify()

    assert sent_payloads == [(batch_id,)]  # no shortage dialog needed, went straight to sending


def test_check_and_notify_opens_the_reconcile_dialog_when_there_is_a_shortage(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    page, batch_id = _closed_batch_with_one_order(conn, monkeypatch, qty=5)
    inv_id = supplier_invoices_core.create_invoice(conn)
    supplier_invoices_core.add_line(conn, inv_id, "Bun kho", 3, "шт", 150, matched_code="BUN01", unit_conversion=1)
    oop.link_invoice_to_batch(conn, inv_id, batch_id)

    opened = []
    monkeypatch.setattr(oop._ShortageReconcileDialog, "exec", lambda self: opened.append(self._shortage) or QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        "shop.ui.online_orders_page.send_arrival_notifications",
        lambda *a, **k: {"sent": [], "failed": []},
    )
    review = oop.BatchReviewDialog(page, conn, batch_id)

    review._check_and_notify()

    assert len(opened) == 1
    assert opened[0][0]["code"] == "BUN01"
    assert opened[0][0]["diff"] == 2  # 5 ordered, 3 delivered


def test_shortage_reconcile_dialog_edit_qty_and_toggle_exclude(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    page, batch_id = _closed_batch_with_one_order(conn, monkeypatch, qty=5)
    inv_id = supplier_invoices_core.create_invoice(conn)
    supplier_invoices_core.add_line(conn, inv_id, "Bun kho", 3, "шт", 150, matched_code="BUN01", unit_conversion=1)
    oop.link_invoice_to_batch(conn, inv_id, batch_id)
    shortage = oop.batch_shortage_report(conn, batch_id)

    dialog = oop._ShortageReconcileDialog(page, conn, batch_id, shortage)
    dialog.shortage_table.selectRow(0)
    assert len(dialog._lines) == 1
    line_id = dialog._lines[0]["line_id"]

    monkeypatch.setattr(QInputDialog, "getDouble", staticmethod(lambda *a, **k: (3, True)))
    dialog.lines_table.selectRow(0)
    dialog._edit_qty()
    assert dialog._lines[0]["qty"] == 3
    assert dialog._lines[0]["original_qty"] == 5

    dialog._toggle_exclude()
    assert dialog._lines[0]["excluded"] is True

    order = list_online_orders(conn)[0]
    assert order["total_estimated"] == 0  # its only line is now excluded
