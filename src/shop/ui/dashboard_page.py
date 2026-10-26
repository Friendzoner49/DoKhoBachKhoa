"""First tab, shown when the app opens: a handful of very large numbers
so the owner can tell at a glance whether to chase customers for money
or set money aside for the supplier -- the original ask behind this
page ("số nợ/lợi nhuận to đùng khi mở app")."""
import sqlite3
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from shop.core.summary import total_customer_debt, total_profit
from shop.core.supplier_invoices import total_unpaid
from shop.ui.branding import icon_path


def _format_rub(n: int) -> str:
    return f"{n:,}".replace(",", ".") + " ₽"


class _HeaderBand(QWidget):
    """Lần 25 (request "điểm nhấn" theme, không đổi toàn bộ giao diện):
    1 dải navy + logo ở đầu tab Tổng quan -- nơi duy nhất mang màu
    thương hiệu, phần còn lại của app vẫn giữ nguyên giao diện Windows
    gốc như đã chốt (xem AskUserQuestion lần 25)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #0b1b2b; border-radius: 10px;")
        self.setFixedHeight(72)

        logo_label = QLabel()
        path = icon_path()
        if path is not None:
            pix = QPixmap(str(path))
            if not pix.isNull():
                logo_label.setPixmap(pix.scaledToHeight(48, Qt.TransformationMode.SmoothTransformation))

        title = QLabel("BachHoa705")
        title.setStyleSheet("color: #5eead4; font-size: 24px; font-weight: 700; background: transparent;")
        subtitle = QLabel("Quản lý bán hàng")
        subtitle.setStyleSheet("color: #89a3b8; font-size: 13px; background: transparent;")

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.addWidget(title)
        text_col.addWidget(subtitle)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 10, 16, 10)
        row.addWidget(logo_label)
        row.addLayout(text_col)
        row.addStretch()


class _BigNumberCard(QWidget):
    def __init__(self, title: str, color: str = "#2a2420", parent=None):
        super().__init__(parent)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; color: #8a7f73;")  # 13px * 1.2 (request #3, lần 19)
        self.value_label = QLabel("—")
        self.value_label.setStyleSheet(f"font-size: 38px; font-weight: 700; color: {color};")  # 32px * 1.2

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str):
        self.value_label.setText(text)


class DashboardPage(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn

        self.customer_debt_card = _BigNumberCard("Khách đang nợ bạn", color="#1a7a3c")
        self.supplier_debt_card = _BigNumberCard("Bạn nợ nhà cung cấp", color="#b5542a")
        self.net_card = _BigNumberCard("Chênh lệch (nợ khách − nợ NCC)")
        self.profit_month_card = _BigNumberCard("Lợi nhuận tháng này")
        self.profit_total_card = _BigNumberCard("Lợi nhuận tất cả thời gian")

        grid = QGridLayout()
        grid.addWidget(self.customer_debt_card, 0, 0)
        grid.addWidget(self.supplier_debt_card, 0, 1)
        grid.addWidget(self.net_card, 1, 0, 1, 2)
        grid.addWidget(self.profit_month_card, 2, 0)
        grid.addWidget(self.profit_total_card, 2, 1)

        hint = QLabel(
            "Chênh lệch dương: khách nợ bạn nhiều hơn bạn nợ nhà cung cấp — có thể đòi nợ khách trước. "
            "Chênh lệch âm: cần lo tiền cho nhà cung cấp trước khi khách trả kịp."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8a7f73; font-size: 14px;")  # 12px * 1.2

        # Lần 19 (request #3): "Công nợ & Lợi nhuận" gộp vào đây làm 1
        # nút, thay vì là tab riêng -- app bớt rối, bớt tab.
        detail_btn = QPushButton("📋 Chi tiết công nợ && lợi nhuận theo khách…")  # "&&" -> literal "&" (Qt mnemonic, see mục 4)
        detail_btn.clicked.connect(self.open_summary_detail)
        detail_row = QHBoxLayout()
        detail_row.addWidget(detail_btn)
        detail_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(_HeaderBand())
        layout.addWidget(hint)
        layout.addLayout(grid)
        layout.addLayout(detail_row)
        layout.addStretch()

        self.refresh()

    def open_summary_detail(self):
        # A fresh SummaryPage each time, owned by this dialog -- simpler
        # and safer than keeping one shared instance alive across opens
        # (no risk of the C++ widget being deleted out from under a
        # reused Python reference once its dialog closes).
        from shop.ui.summary_page import SummaryPage

        dialog = QDialog(self)
        dialog.setWindowTitle("Công nợ & lợi nhuận theo khách")
        dialog.resize(768, 576)  # 640x480 * 1.2
        layout = QVBoxLayout(dialog)
        layout.addWidget(SummaryPage(self.conn))
        dialog.exec()

    def refresh(self):
        customer_debt = total_customer_debt(self.conn)
        supplier_debt = total_unpaid(self.conn)
        month_start = date.today().replace(day=1).isoformat()

        self.customer_debt_card.set_value(_format_rub(customer_debt))
        self.supplier_debt_card.set_value(_format_rub(supplier_debt))
        self.net_card.set_value(_format_rub(customer_debt - supplier_debt))
        self.profit_month_card.set_value(_format_rub(total_profit(self.conn, date_from=month_start)))
        self.profit_total_card.set_value(_format_rub(total_profit(self.conn)))
