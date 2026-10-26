import sqlite3

from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shop.core.customers import add_customer, get_customer, list_customers, update_customer
from shop.core.payments import add_payment
from shop.core.summary import customer_debt
from shop.ui.dialogs import CustomerDialog, PaymentDialog, PaymentsListDialog

HEADERS = ["Tên khách hàng", "Địa chỉ", "Liên hệ", "% markup", "Công nợ hiện tại (RUB)", "Hoạt động"]


class CustomersPage(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        add_btn = QPushButton("Thêm khách hàng")
        add_btn.clicked.connect(self.add_customer_dialog)
        edit_btn = QPushButton("Sửa")
        edit_btn.clicked.connect(self.edit_customer_dialog)
        toggle_btn = QPushButton("Ngừng/Mở hoạt động")
        toggle_btn.clicked.connect(self.toggle_active)
        payment_btn = QPushButton("Ghi nhận thanh toán")
        payment_btn.clicked.connect(self.record_payment)
        history_btn = QPushButton("Lịch sử thanh toán")
        history_btn.clicked.connect(self.show_payment_history)

        buttons = QHBoxLayout()
        buttons.addWidget(add_btn)
        buttons.addWidget(edit_btn)
        buttons.addWidget(toggle_btn)
        buttons.addStretch()
        buttons.addWidget(payment_btn)
        buttons.addWidget(history_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        customers = list_customers(self.conn, active_only=False)
        self.table.setRowCount(len(customers))
        self._ids = []
        for row, c in enumerate(customers):
            self._ids.append(c["id"])
            debt = customer_debt(self.conn, c["id"])
            values = [
                c["name"],
                c["address"] or "",
                c["contact"] or "",
                f"{c['default_markup_pct']:g}",
                f"{debt:,}".replace(",", "."),
                "Có" if c["active"] else "Không",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            return None
        return self._ids[row]

    def add_customer_dialog(self):
        dialog = CustomerDialog(self)
        if dialog.exec():
            values = dialog.values()
            if not values["name"]:
                QMessageBox.warning(self, "Thiếu thông tin", "Cần nhập tên khách hàng.")
                return
            add_customer(self.conn, **values)
            self.refresh()

    def edit_customer_dialog(self):
        customer_id = self._selected_id()
        if customer_id is None:
            return
        customer = get_customer(self.conn, customer_id)
        dialog = CustomerDialog(self, customer=customer)
        if dialog.exec():
            update_customer(self.conn, customer_id, **dialog.values())
            self.refresh()

    def toggle_active(self):
        customer_id = self._selected_id()
        if customer_id is None:
            return
        customer = get_customer(self.conn, customer_id)
        update_customer(self.conn, customer_id, active=int(not customer["active"]))
        self.refresh()

    def record_payment(self):
        customer_id = self._selected_id()
        if customer_id is None:
            QMessageBox.information(self, "Chọn khách hàng", "Hãy chọn một khách hàng trước.")
            return
        dialog = PaymentDialog(self)
        if dialog.exec():
            add_payment(self.conn, customer_id, **dialog.values())
            self.refresh()

    def show_payment_history(self):
        customer_id = self._selected_id()
        if customer_id is None:
            QMessageBox.information(self, "Chọn khách hàng", "Hãy chọn một khách hàng trước.")
            return
        customer = get_customer(self.conn, customer_id)
        dialog = PaymentsListDialog(self, self.conn, customer_id, customer["name"])
        dialog.exec()
        self.refresh()  # a deleted payment changes the debt column
