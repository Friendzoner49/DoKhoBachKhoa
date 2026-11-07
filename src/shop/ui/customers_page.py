import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shop.core.customers import add_customer, delete_customer, get_customer, list_customers, update_customer
from shop.core.online_orders import known_telegram_chats, link_customer, unlink_customer
from shop.core.payments import add_payment
from shop.core.summary import customer_debt, unpaid_invoices
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
        delete_btn = QPushButton("🗑 Xóa khách hàng")
        delete_btn.clicked.connect(self.delete_customer_dialog)
        link_btn = QPushButton("🔗 Liên kết Telegram…")
        link_btn.clicked.connect(self.link_telegram_dialog)
        payment_btn = QPushButton("Ghi nhận thanh toán")
        payment_btn.clicked.connect(self.record_payment)
        history_btn = QPushButton("Lịch sử thanh toán")
        history_btn.clicked.connect(self.show_payment_history)

        buttons = QHBoxLayout()
        buttons.addWidget(add_btn)
        buttons.addWidget(edit_btn)
        buttons.addWidget(toggle_btn)
        buttons.addWidget(delete_btn)
        buttons.addWidget(link_btn)
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
                ("Có" if c["active"] else "Không") + (" · dùng nội bộ" if c["internal"] else ""),
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

    def delete_customer_dialog(self):
        customer_id = self._selected_id()
        if customer_id is None:
            return
        customer = get_customer(self.conn, customer_id)
        confirm = QMessageBox.question(
            self,
            "Xóa khách hàng",
            f'Xóa hẳn khách hàng "{customer["name"]}"? Không thể hoàn tác.',
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_customer(self.conn, customer_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Không thể xóa", str(exc))
            return
        self.refresh()

    def link_telegram_dialog(self):
        customer_id = self._selected_id()
        if customer_id is None:
            QMessageBox.information(self, "Chọn khách hàng", "Hãy chọn một khách hàng trước.")
            return
        customer = get_customer(self.conn, customer_id)
        chats = known_telegram_chats(self.conn)
        if not chats:
            QMessageBox.information(
                self, "Chưa có chat nào",
                'Chưa có khách nào đặt đơn qua bot. Bấm "Đồng bộ từ Telegram" ở tab Đơn hàng online trước.',
            )
            return
        names = {c["id"]: c["name"] for c in list_customers(self.conn, active_only=False)}
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Liên kết Telegram — {customer['name']}")
        dialog.resize(520, 420)
        hint = QLabel(
            f'Tích các chat Telegram thuộc về "{customer["name"]}". Chat đang gắn với khách khác sẽ được chuyển sang '
            "khách này. Hóa đơn gửi qua Telegram chỉ đến đúng các chat được tích."
        )
        hint.setWordWrap(True)
        listing = QListWidget()
        for chat in chats:
            owner = chat["customer_id"]
            suffix = "" if owner is None else (" — đang gắn: " + names.get(owner, f"#{owner}") if owner != customer_id else "")
            item = QListWidgetItem(f"{chat['label']} · id {chat['chat_id']}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, chat["chat_id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if owner == customer_id else Qt.CheckState.Unchecked)
            listing.addItem(item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(hint)
        layout.addWidget(listing)
        layout.addWidget(buttons)
        if not dialog.exec():
            return
        for i in range(listing.count()):
            item = listing.item(i)
            chat_id = item.data(Qt.ItemDataRole.UserRole)
            was_mine = next(c for c in chats if c["chat_id"] == chat_id)["customer_id"] == customer_id
            checked = item.checkState() == Qt.CheckState.Checked
            if checked:
                link_customer(self.conn, chat_id, customer_id)
            elif was_mine:
                unlink_customer(self.conn, chat_id)
        self.refresh()

    def record_payment(self):
        customer_id = self._selected_id()
        if customer_id is None:
            QMessageBox.information(self, "Chọn khách hàng", "Hãy chọn một khách hàng trước.")
            return
        dialog = PaymentDialog(
            self, unpaid=unpaid_invoices(self.conn, customer_id), debt=max(customer_debt(self.conn, customer_id), 0)
        )
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
