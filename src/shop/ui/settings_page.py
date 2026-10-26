"""'Cài đặt' tab: the 2 admin actions that are either destructive (factory
reset) or replace the whole ledger (import a package from another
machine) -- deliberately kept off every other tab so they're never one
misclick away from a normal day's work."""
import sqlite3
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shop.core.reset import reset_transactional_data, transactional_counts
from shop.core.transfer import TransferError, default_export_name, export_package, import_package, read_manifest
from shop.db.backup import backup_now
from shop.paths import bot_sync_settings, db_path, set_bot_sync_settings, supplier_invoices_dir
from shop.ui.dialogs import TypedConfirmDialog


class SettingsPage(QWidget):
    def __init__(self, conn: sqlite3.Connection, main_window, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.main_window = main_window

        transfer_box = QGroupBox("Chuyển dữ liệu sang máy khác")
        transfer_layout = QVBoxLayout(transfer_box)
        transfer_layout.addWidget(
            _wrapped_label(
                "Xuất toàn bộ dữ liệu (danh mục, khách hàng, hóa đơn, công nợ, ảnh hóa đơn nhà cung cấp) "
                "ra 1 file duy nhất để chép sang máy khác (USB, Drive...). Nhập lại file đó trên máy kia "
                "sẽ THAY THẾ TOÀN BỘ dữ liệu đang có trên máy đó."
            )
        )
        export_btn = QPushButton("Xuất dữ liệu ra file…")
        export_btn.clicked.connect(self.export_data)
        import_btn = QPushButton("Nhập dữ liệu từ file…")
        import_btn.clicked.connect(self.import_data)
        transfer_buttons = QHBoxLayout()
        transfer_buttons.addWidget(export_btn)
        transfer_buttons.addWidget(import_btn)
        transfer_buttons.addStretch()
        transfer_layout.addLayout(transfer_buttons)

        reset_box = QGroupBox("Khôi phục cài đặt gốc")
        reset_layout = QVBoxLayout(reset_box)
        reset_layout.addWidget(
            _wrapped_label(
                "Xóa VĨNH VIỄN khách hàng, hóa đơn, thanh toán, hóa đơn nhà cung cấp và đơn hàng online -- "
                "dùng để dọn sạch dữ liệu dùng thử trước khi bắt đầu dùng thật. "
                "Danh mục hàng (giá vốn, ảnh, nhóm hàng) được GIỮ NGUYÊN."
            )
        )
        reset_btn = QPushButton("Khôi phục cài đặt gốc…")
        reset_btn.clicked.connect(self.factory_reset)
        reset_row = QHBoxLayout()
        reset_row.addWidget(reset_btn)
        reset_row.addStretch()
        reset_layout.addLayout(reset_row)

        layout = QVBoxLayout(self)
        layout.addWidget(transfer_box)
        layout.addWidget(reset_box)
        layout.addStretch()

    def refresh(self):
        pass  # nothing here depends on live data counts until a button is pressed

    # ---- Chuyển dữ liệu ----

    def export_data(self):
        default_path = str(Path.home() / default_export_name())
        path, _ = QFileDialog.getSaveFileName(self, "Xuất dữ liệu ra file", default_path, "Gói dữ liệu BachHoa705 (*.shopdata)")
        if not path:
            return
        if not path.endswith(".shopdata"):
            path += ".shopdata"
        worker_url, sync_secret = bot_sync_settings()
        try:
            dest = export_package(self.conn, Path(path), supplier_invoices_dir(), worker_url, sync_secret)
        except OSError as exc:
            QMessageBox.critical(self, "Xuất thất bại", str(exc))
            return
        QMessageBox.information(self, "Đã xuất dữ liệu", f"Đã lưu vào:\n{dest}\n\nChép file này sang máy kia rồi dùng \"Nhập dữ liệu từ file…\" ở đó.")

    def import_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "Nhập dữ liệu từ file", "", "Gói dữ liệu BachHoa705 (*.shopdata)")
        if not path:
            return

        current_version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        try:
            manifest = read_manifest(Path(path), current_version)
        except TransferError as exc:
            QMessageBox.warning(self, "Không đọc được gói dữ liệu", str(exc))
            return

        current = transactional_counts(self.conn)
        current_products = self.conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        message = (
            f"Dữ liệu đang có trên MÁY NÀY: {current_products} mặt hàng, {current['customers']} khách hàng, "
            f"{current['invoices']} hóa đơn.\n\n"
            f"Gói sắp nhập: xuất lúc {manifest.exported_at.replace('T', ' ')}"
            + (f" từ máy \"{manifest.source_machine}\"" if manifest.source_machine else "")
            + f" -- có {manifest.products} mặt hàng, {manifest.customers} khách hàng, {manifest.invoices} hóa đơn.\n\n"
            "NHẬP SẼ XÓA VÀ THAY THẾ TOÀN BỘ dữ liệu đang có trên máy này bằng dữ liệu trong gói. "
            "Không có cách hoàn tác ngoài khôi phục bản sao lưu.\n\n"
            "App sẽ tự đóng sau khi nhập xong -- mở lại app để thấy dữ liệu mới."
        )
        dialog = TypedConfirmDialog(self, "Xác nhận nhập dữ liệu", message)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        try:
            backup_now()  # safety net on top of whatever backup already exists, right before a full replace
            self.conn.close()  # Windows can't replace a file this process still has open
            manifest = import_package(Path(path), current_version, db_path(), supplier_invoices_dir())
        except TransferError as exc:
            QMessageBox.critical(self, "Nhập thất bại", str(exc))
            return

        # Only fill in sync settings if THIS machine doesn't already have
        # its own -- never silently overwrite a machine that's already
        # configured for its own Worker.
        existing_url, existing_secret = bot_sync_settings()
        if not existing_url and not existing_secret and (manifest.bot_sync_url or manifest.bot_sync_secret):
            set_bot_sync_settings(manifest.bot_sync_url, manifest.bot_sync_secret)

        QMessageBox.information(
            self,
            "Đã nhập dữ liệu",
            "Đã nhập xong. App sẽ đóng lại ngay bây giờ -- mở lại app để thấy dữ liệu mới.",
        )
        QApplication.instance().quit()

    # ---- Khôi phục cài đặt gốc ----

    def factory_reset(self):
        counts = transactional_counts(self.conn)
        products = self.conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        message = (
            f"Sẽ xóa VĨNH VIỄN: {counts['customers']} khách hàng, {counts['invoices']} hóa đơn, "
            f"{counts['payments']} khoản thanh toán, {counts['supplier_invoices']} hóa đơn nhà cung cấp, "
            f"{counts['online_orders']} đơn hàng online.\n\n"
            f"Danh mục hàng ({products} mặt hàng -- giá vốn, ảnh, nhóm hàng) được GIỮ NGUYÊN. Giá vốn đã đổi "
            "qua các lần \"Áp dụng giá mới\" từ hóa đơn nhà cung cấp trước đó sẽ KHÔNG được hoàn tác.\n\n"
            "Một bản sao lưu sẽ được tạo trước khi xóa, nhưng hành động này không thể hoàn tác qua giao diện."
        )
        dialog = TypedConfirmDialog(self, "Xác nhận khôi phục cài đặt gốc", message)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        backup_now()
        reset_transactional_data(self.conn)
        self.main_window.refresh_all_tabs()
        QMessageBox.information(self, "Đã khôi phục cài đặt gốc", "Đã xóa dữ liệu giao dịch. Danh mục hàng vẫn còn nguyên.")


def _wrapped_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label
