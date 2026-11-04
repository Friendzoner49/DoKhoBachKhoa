import sqlite3
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shop.core.customers import list_customers
from shop.core.summary import customer_debt, customer_profit
from shop.excel.summary_export import export_summary

HEADERS = ["Khách hàng", "Công nợ hiện tại (RUB)", "Lợi nhuận (tất cả thời gian, RUB)"]


class SummaryPage(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        refresh_btn = QPushButton("Làm mới")
        refresh_btn.clicked.connect(self.refresh)
        export_btn = QPushButton("Xuất Excel")
        export_btn.clicked.connect(self.export_excel)

        buttons = QHBoxLayout()
        buttons.addWidget(refresh_btn)
        buttons.addStretch()
        buttons.addWidget(export_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        customers = list_customers(self.conn, active_only=False)
        self.table.setRowCount(len(customers))
        for row, c in enumerate(customers):
            debt = customer_debt(self.conn, c["id"])
            profit = customer_profit(self.conn, c["id"])
            values = [c["name"], f"{debt:,}".replace(",", "."), f"{profit:,}".replace(",", ".")]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "Xuất công nợ & lợi nhuận", "cong-no-loi-nhuan.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        export_summary(self.conn, Path(path))
        QMessageBox.information(self, "Đã xuất", f"Đã lưu file vào:\n{path}")
