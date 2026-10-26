import sqlite3

from PySide6.QtWidgets import QMainWindow, QTabWidget

from shop.ui.customers_page import CustomersPage
from shop.ui.dashboard_page import DashboardPage
from shop.ui.invoices_page import InvoicesPage
from shop.ui.online_orders_page import OnlineOrdersPage
from shop.ui.products_page import ProductsPage
from shop.ui.settings_page import SettingsPage
from shop.ui.summary_page import SummaryPage
from shop.ui.supplier_invoices_page import SupplierInvoicesPage


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self.setWindowTitle("BachHoa705 — Quản lý bán hàng")
        self.resize(1200, 780)  # 1000x650 * 1.2 (request #3, lần 19 -- chữ/nút to hơn cần cửa sổ rộng hơn)

        tabs = QTabWidget()
        self.dashboard_page = DashboardPage(conn)
        self.products_page = ProductsPage(conn)
        self.customers_page = CustomersPage(conn)
        self.invoices_page = InvoicesPage(conn)
        self.summary_page = SummaryPage(conn)
        self.supplier_invoices_page = SupplierInvoicesPage(conn)
        self.online_orders_page = OnlineOrdersPage(conn)
        self.settings_page = SettingsPage(conn, self)

        # Dashboard first, so the big debt/profit numbers are the first
        # thing shown when the app opens. "Công nợ & Lợi nhuận" is no
        # longer its own tab (lần 19, request #3: fewer tabs) -- its
        # content is now the "Chi tiết…" button on the dashboard, which
        # builds its own SummaryPage per open. self.summary_page below
        # is kept only so self_test() can still exercise/screenshot it
        # without going through that button's click handler.
        tabs.addTab(self.dashboard_page, "Tổng quan")
        tabs.addTab(self.products_page, "Danh mục hàng")
        tabs.addTab(self.customers_page, "Khách hàng")
        tabs.addTab(self.invoices_page, "Hóa đơn")
        tabs.addTab(self.supplier_invoices_page, "Hóa đơn nhà cung cấp")
        tabs.addTab(self.online_orders_page, "Đơn hàng online")
        tabs.addTab(self.settings_page, "Cài đặt")
        tabs.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(tabs)
        self._tabs = tabs

    def _on_tab_changed(self, index: int):
        # Cheap refresh-on-view instead of wiring cross-page change signals,
        # since this app is small enough that re-querying SQLite is instant.
        widget = self._tabs.widget(index)
        if hasattr(widget, "refresh"):
            widget.refresh()

    def refresh_all_tabs(self):
        """Called after an action that changes data out from under every
        tab at once (factory reset) -- so numbers don't look stale on a
        tab the user doesn't happen to click into next."""
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            if hasattr(widget, "refresh"):
                widget.refresh()
