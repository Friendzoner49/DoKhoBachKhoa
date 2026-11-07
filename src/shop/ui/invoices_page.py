import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shop.core.customers import get_customer, list_customers
from shop.core.invoice_send import InvoiceSendError, build_invoice_message, send_invoice_to_customer
from shop.core.invoices import create_invoice, get_invoice, list_invoices
from shop.paths import bot_sync_settings
from shop.ui.invoice_editor import InvoiceEditorDialog

HEADERS = ["#", "Khách hàng", "Ngày", "Trạng thái", "Tổng tiền (RUB)", "Đã gửi Telegram"]
STATUS_LABELS = {"draft": "Nháp", "finalized": "Đã hoàn tất", "cancelled": "Đã hủy"}


class InvoicesPage(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn

        self.customer_combo = QComboBox()
        new_btn = QPushButton("Tạo hóa đơn mới")
        new_btn.clicked.connect(self.new_invoice)
        open_btn = QPushButton("Mở hóa đơn")
        open_btn.clicked.connect(self.open_selected)

        top = QHBoxLayout()
        top.addWidget(self.customer_combo, 1)
        top.addWidget(new_btn)
        top.addWidget(open_btn)
        send_btn = QPushButton("📨 Gửi hóa đơn cho khách (Telegram)")
        send_btn.setToolTip(
            "Gửi bản tóm tắt bằng chữ của hóa đơn đang chọn cho khách đó qua Telegram.\n"
            "Chỉ gửi được hóa đơn đã hoàn tất, và khách phải đã liên kết Telegram."
        )
        send_btn.clicked.connect(self.send_selected)
        top.addWidget(send_btn)
        copy_btn = QPushButton("📋 Copy nội dung hóa đơn")
        copy_btn.setToolTip(
            "Chép bản tóm tắt hóa đơn đang chọn để tự dán vào Zalo/Telegram cho khách chưa liên kết bot."
        )
        copy_btn.clicked.connect(self.copy_selected)
        top.addWidget(copy_btn)

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
        self._customers = list_customers(self.conn, active_only=True)
        self.customer_combo.clear()
        for c in self._customers:
            self.customer_combo.addItem(c["name"], c["id"])

        self._invoice_ids = []
        invoices = list_invoices(self.conn)
        self.table.setRowCount(len(invoices))
        customers_by_id = {c["id"]: c["name"] for c in list_customers(self.conn, active_only=False)}
        for row, inv in enumerate(invoices):
            self._invoice_ids.append(inv["id"])
            total = get_invoice(self.conn, inv["id"])["total"]
            values = [
                str(inv["id"]),
                customers_by_id.get(inv["customer_id"], "?"),
                inv["invoice_date"],
                STATUS_LABELS.get(inv["status"], inv["status"]),
                f"{total:,}".replace(",", "."),
                "Có" if self.conn.execute("SELECT telegram_sent_at FROM invoices WHERE id = ?", (inv["id"],)).fetchone()[0] else "",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def new_invoice(self):
        if self.customer_combo.count() == 0:
            QMessageBox.information(self, "Chưa có khách hàng", "Hãy thêm khách hàng trước ở tab Khách hàng.")
            return
        customer_id = self.customer_combo.currentData()
        invoice_id = create_invoice(self.conn, customer_id)
        self.refresh()
        self._open_editor(invoice_id)

    def open_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._invoice_ids):
            return
        self._open_editor(self._invoice_ids[row])

    def copy_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._invoice_ids):
            QMessageBox.information(self, "Chưa chọn hóa đơn", "Bấm chọn 1 hóa đơn trong danh sách trước.")
            return
        QApplication.clipboard().setText(build_invoice_message(self.conn, self._invoice_ids[row]))
        QMessageBox.information(self, "Đã copy", "Đã copy nội dung hóa đơn — dán (Ctrl+V) vào tin nhắn cho khách.")

    def send_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._invoice_ids):
            QMessageBox.information(self, "Chưa chọn hóa đơn", "Bấm chọn 1 hóa đơn trong danh sách trước.")
            return
        invoice_id = self._invoice_ids[row]
        invoice = get_invoice(self.conn, invoice_id)
        customer = get_customer(self.conn, invoice["customer_id"])
        already = self.conn.execute("SELECT telegram_sent_at FROM invoices WHERE id = ?", (invoice_id,)).fetchone()[0]
        text = (
            f"Gửi hóa đơn #{invoice_id} ({invoice['total']:,} ₽) cho khách \"{customer['name']}\" qua Telegram?\n"
            "Tin nhắn KHÔNG thể thu hồi sau khi gửi."
        ).replace(",", ".")
        if already:
            text += "\n\n⚠ Hóa đơn này ĐÃ gửi trước đó — gửi nữa khách sẽ nhận 2 tin."
        if QMessageBox.question(self, "Gửi hóa đơn?", text) != QMessageBox.StandardButton.Yes:
            return
        worker_url, sync_secret = bot_sync_settings()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            sent = send_invoice_to_customer(self.conn, invoice_id, worker_url, sync_secret)
        except InvoiceSendError as e:
            QMessageBox.warning(self, "Không gửi được", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "Đã gửi", f"Đã gửi hóa đơn cho khách \"{customer['name']}\" ({sent} cuộc trò chuyện).")
        self.refresh()

    def _open_editor(self, invoice_id: int):
        dialog = InvoiceEditorDialog(self, self.conn, invoice_id)
        dialog.exec()
        self.refresh()
