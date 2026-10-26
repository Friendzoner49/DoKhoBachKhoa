"""Dialog for editing one invoice's lines: add/remove products, edit
qty/cost/price inline, then finalize and/or export to Excel.

A draft line's "Giá vốn" (cost) starts at whatever the catalog said
when the line was added, but stays editable until finalized -- costs
change between when a line is added (e.g. from a pasted Telegram
order) and when the invoice is actually finalized, and the owner needs
to be able to correct it so profit isn't computed from a stale cost.

A finalized invoice is read-only here — edit cost/price going forward
by starting a new invoice (or "Mở lại để sửa"), so the old snapshot
(and therefore past debt/profit) never changes on its own. See
shop.core.invoices.
"""
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from shop.core import invoices as invoices_core
from shop.core.customers import get_customer
from shop.core.pricing import round_rub
from shop.core.products import list_products
from shop.excel.invoice_export import export_invoice
from shop.ui.dialogs import CustomLineDialog, ProductPickerDialog

COL_CODE, COL_NAME, COL_UNIT, COL_QTY, COL_COST, COL_PRICE, COL_TOTAL = range(7)
HEADERS = ["Mã hàng", "Tên mặt hàng", "Đơn vị", "Số lượng", "Giá vốn (RUB)", "Đơn giá (RUB)", "Thành tiền (RUB)"]
EDITABLE_COLS = {COL_QTY, COL_COST, COL_PRICE}


class InvoiceEditorDialog(QDialog):
    def __init__(self, parent, conn: sqlite3.Connection, invoice_id: int):
        super().__init__(parent)
        self.conn = conn
        self.invoice_id = invoice_id
        self._line_ids: list[int] = []

        invoice = invoices_core.get_invoice(conn, invoice_id)
        customer = get_customer(conn, invoice["customer_id"])
        self.customer = customer
        self.is_draft = invoice["status"] == "draft"

        self.setWindowTitle(f"Hóa đơn #{invoice_id} — {customer['name']}")
        self.resize(768, 576)  # 640x480 * 1.2 (request #3, lần 19)

        self.info_label = QLabel()
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.itemChanged.connect(self._on_item_changed)

        self.add_line_btn = QPushButton("Thêm dòng")
        self.add_line_btn.clicked.connect(self.add_line)
        self.add_fee_btn = QPushButton("Thêm phí dịch vụ…")
        self.add_fee_btn.clicked.connect(self.add_custom_fee)
        self.remove_line_btn = QPushButton("Xóa dòng")
        self.remove_line_btn.clicked.connect(self.remove_line)
        self.finalize_btn = QPushButton("Hoàn tất hóa đơn")
        self.finalize_btn.clicked.connect(self.finalize)
        self.reopen_btn = QPushButton("Mở lại để sửa")
        self.reopen_btn.clicked.connect(self.reopen)
        self.cancel_btn = QPushButton("Hủy hóa đơn")
        self.cancel_btn.clicked.connect(self.cancel)
        self.delete_draft_btn = QPushButton("Xóa hóa đơn nháp (trống)")
        self.delete_draft_btn.clicked.connect(self.delete_draft)
        export_btn = QPushButton("Xuất Excel")
        export_btn.clicked.connect(self.export_excel)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)

        top_buttons = QHBoxLayout()
        top_buttons.addWidget(self.add_line_btn)
        top_buttons.addWidget(self.add_fee_btn)
        top_buttons.addWidget(self.remove_line_btn)
        top_buttons.addWidget(self.delete_draft_btn)
        top_buttons.addStretch()
        top_buttons.addWidget(self.reopen_btn)
        top_buttons.addWidget(self.cancel_btn)
        top_buttons.addWidget(self.finalize_btn)

        bottom_buttons = QHBoxLayout()
        bottom_buttons.addWidget(export_btn)
        bottom_buttons.addStretch()
        bottom_buttons.addWidget(close_btn)

        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-weight: bold;")

        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addLayout(top_buttons)
        layout.addWidget(self.table)
        layout.addWidget(self.total_label)
        layout.addLayout(bottom_buttons)

        self.refresh()

    def refresh(self):
        invoice = invoices_core.get_invoice(self.conn, self.invoice_id)
        self.is_draft = invoice["status"] == "draft"
        self.status = invoice["status"]
        status_text = {"draft": "NHÁP", "finalized": "ĐÃ HOÀN TẤT", "cancelled": "ĐÃ HỦY"}[invoice["status"]]
        self.info_label.setText(
            f"Khách hàng: {self.customer['name']}  |  Ngày: {invoice['invoice_date']}  |  Trạng thái: {status_text}"
        )

        self.table.blockSignals(True)
        lines = invoice["lines"]
        self._line_ids = [line["id"] for line in lines]
        self.table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            values = [None] * 7
            values[COL_CODE] = line["product_code"]
            values[COL_NAME] = line["product_name_snapshot"]
            values[COL_UNIT] = line["unit_snapshot"] or ""
            values[COL_QTY] = f"{line['qty']:g}"
            values[COL_COST] = f"{line['cost_price_snapshot']:g}"
            values[COL_PRICE] = f"{line['unit_price']:g}"
            values[COL_TOTAL] = f"{line['line_total']:,}".replace(",", ".")
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col not in EDITABLE_COLS or not self.is_draft:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)

        self.total_label.setText(f"TỔNG CỘNG: {invoice['total']:,} RUB".replace(",", "."))

        self.add_line_btn.setEnabled(self.is_draft)
        self.add_fee_btn.setEnabled(self.is_draft)
        self.remove_line_btn.setEnabled(self.is_draft)
        self.finalize_btn.setEnabled(self.is_draft and len(lines) > 0)
        self.reopen_btn.setEnabled(self.status == "finalized")
        self.cancel_btn.setEnabled(self.status in ("draft", "finalized"))
        self.delete_draft_btn.setEnabled(self.is_draft and len(lines) == 0)

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        if row >= len(self._line_ids):
            return
        line_id = self._line_ids[row]
        try:
            qty = float(self.table.item(row, COL_QTY).text().replace(",", "."))
            cost_price_value = float(self.table.item(row, COL_COST).text().replace(",", "."))
            unit_price_value = round_rub(self.table.item(row, COL_PRICE).text().replace(",", "."))
        except (ValueError, ArithmeticError):
            QMessageBox.warning(self, "Giá trị không hợp lệ", "Số lượng, giá vốn và đơn giá phải là số.")
            self.refresh()
            return
        invoices_core.update_line(
            self.conn, line_id, qty=qty, unit_price_value=unit_price_value, cost_price_value=cost_price_value
        )
        self.refresh()

    def add_line(self):
        products = list_products(self.conn, active_only=True)
        picker = ProductPickerDialog(self, products)
        if picker.exec() and picker.selected_code:
            invoices_core.add_line(
                self.conn,
                self.invoice_id,
                picker.selected_code,
                qty=1,
                markup_pct=self.customer["default_markup_pct"],
            )
            self.refresh()

    def add_custom_fee(self):
        dialog = CustomLineDialog(self)
        if dialog.exec():
            invoices_core.add_custom_line(self.conn, self.invoice_id, **dialog.values())
            self.refresh()

    def remove_line(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._line_ids):
            return
        invoices_core.remove_line(self.conn, self._line_ids[row])
        self.refresh()

    def finalize(self):
        confirm = QMessageBox.question(
            self,
            "Hoàn tất hóa đơn",
            "Sau khi hoàn tất, hóa đơn sẽ tính vào công nợ và không sửa được nữa. Tiếp tục?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            invoices_core.finalize_invoice(self.conn, self.invoice_id)
            self.refresh()

    def reopen(self):
        confirm = QMessageBox.question(
            self,
            "Mở lại để sửa",
            "Hóa đơn sẽ trở về trạng thái nháp và tạm thời không tính vào công nợ cho đến khi hoàn tất lại. Tiếp tục?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            invoices_core.reopen_invoice(self.conn, self.invoice_id)
            self.refresh()

    def cancel(self):
        confirm = QMessageBox.question(
            self,
            "Hủy hóa đơn",
            "Hóa đơn đã hủy sẽ không tính vào công nợ/lợi nhuận nữa, nhưng vẫn giữ lại để xem lịch sử. Tiếp tục?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            invoices_core.cancel_invoice(self.conn, self.invoice_id)
            self.refresh()

    def delete_draft(self):
        confirm = QMessageBox.question(self, "Xóa hóa đơn nháp", "Xóa hẳn hóa đơn nháp trống này?")
        if confirm == QMessageBox.StandardButton.Yes:
            invoices_core.delete_draft_invoice(self.conn, self.invoice_id)
            self.accept()  # nothing left to show; close the editor

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Xuất hóa đơn ra Excel", f"hoa-don-{self.invoice_id}.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        export_invoice(self.conn, self.invoice_id, Path(path))
        QMessageBox.information(self, "Đã xuất", f"Đã lưu hóa đơn vào:\n{path}")
