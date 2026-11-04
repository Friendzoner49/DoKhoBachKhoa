import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shop.core.customers import list_customers
from shop.core.invoices import create_invoice, get_invoice, list_invoices
from shop.ui.invoice_editor import InvoiceEditorDialog

HEADERS = ["#", "Khách hàng", "Ngày", "Trạng thái", "Tổng tiền (RUB)"]
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

    def _open_editor(self, invoice_id: int):
        dialog = InvoiceEditorDialog(self, self.conn, invoice_id)
        dialog.exec()
        self.refresh()
