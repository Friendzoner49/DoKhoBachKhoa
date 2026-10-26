import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shop.core.supplier_invoices import SyncError, list_invoices, sync_photos_from_bot
from shop.paths import bot_sync_settings, supplier_invoices_dir
from shop.ui.dialogs import BotSyncSettingsDialog
from shop.ui.supplier_invoice_dialog import SupplierInvoiceDialog

HEADERS = ["#", "Số hóa đơn", "Ngày", "Ghi chú", "Tổng tiền (RUB)", "Đã thanh toán?", "Đã áp dụng giá?"]


class SupplierInvoicesPage(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn

        new_btn = QPushButton("Nhập hóa đơn nhà cung cấp mới…")
        new_btn.clicked.connect(self.new_invoice)
        open_btn = QPushButton("Mở / Sửa")
        open_btn.clicked.connect(self.open_selected)
        # Ảnh gửi vào group Telegram bằng lệnh "/hangve" (lần 20) --
        # dùng chung Worker URL + Mã đồng bộ với tab "Đơn hàng online",
        # cài 1 lần ở đó là đủ (xem shop.ui.online_orders_page).
        sync_btn = QPushButton("🔄 Đồng bộ ảnh từ Telegram")
        sync_btn.clicked.connect(self.sync_photos_now)

        top = QHBoxLayout()
        top.addWidget(new_btn)
        top.addWidget(open_btn)
        top.addWidget(sync_btn)
        top.addStretch()

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.open_selected)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        invoices = list_invoices(self.conn)
        self._ids = [inv["id"] for inv in invoices]
        self.table.setRowCount(len(invoices))
        for row, inv in enumerate(invoices):
            values = [
                str(inv["id"]),
                inv["invoice_number"] or "",
                inv["invoice_date"] or "",
                inv.get("note") or "",
                f"{inv['total_amount']:,}".replace(",", "."),
                "Có" if inv["paid"] else "Không",
                "Có" if inv["applied_at"] else "Không",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def new_invoice(self):
        dialog = SupplierInvoiceDialog(self, self.conn)
        dialog.exec()
        self.refresh()

    def open_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            return
        dialog = SupplierInvoiceDialog(self, self.conn, invoice_id=self._ids[row])
        dialog.exec()
        self.refresh()

    def sync_photos_now(self):
        worker_url, sync_secret = bot_sync_settings()
        if not worker_url or not sync_secret:
            dialog = BotSyncSettingsDialog(self, worker_url, sync_secret)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            from shop.paths import set_bot_sync_settings

            set_bot_sync_settings(*dialog.values())
            worker_url, sync_secret = dialog.values()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            inserted = sync_photos_from_bot(self.conn, worker_url, sync_secret, supplier_invoices_dir())
        except SyncError as e:
            QMessageBox.warning(self, "Không đồng bộ được", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh()
        if inserted > 0:
            QMessageBox.information(self, "Đã đồng bộ", f"Có {inserted} ảnh hóa đơn mới từ Telegram.")
        else:
            QMessageBox.information(self, "Đã đồng bộ", "Không có ảnh hóa đơn mới.")
