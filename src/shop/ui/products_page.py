import sqlite3
from datetime import date

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shop.core.channel_announce import AnnounceError, announce_product
from shop.core.products import (
    get_product,
    list_categories,
    list_products,
    set_active,
    set_image_filename,
    set_in_stock,
    set_sale_until,
    upsert_product,
)
from shop.excel.catalog_export import export_catalog
from shop.paths import bot_sync_settings, site_repo_dir
from shop.tools.import_xlsx import import_catalog
from shop.tools.publish_site import publish as publish_site
from shop.ui.dialogs import ProductDialog
from shop.ui.local_image import LocalImageError, apply_local_image

HEADERS = ["Mã hàng", "Tên mặt hàng", "Đơn vị", "Nhóm hàng", "Giá vốn", "SL sỉ", "Hạn bán", "Tình trạng"]


class ProductsPage(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        add_btn = QPushButton("Thêm mặt hàng")
        add_btn.clicked.connect(self.add_product)
        edit_btn = QPushButton("Sửa")
        edit_btn.clicked.connect(self.edit_product)
        toggle_btn = QPushButton("Ngừng bán / Mở bán lại")
        toggle_btn.clicked.connect(self.toggle_active)
        delete_btn = QPushButton("🗑 Xóa khỏi danh mục")
        delete_btn.setToolTip(
            "Dùng cho mặt hàng theo mùa/bán giới hạn chỉ bán 1 lần, không dùng lại nữa.\n"
            "Ẩn hoàn toàn khỏi app và website (không xóa dữ liệu thật — hóa đơn cũ không bị ảnh hưởng).\n"
            "Tích \"Hiện cả mặt hàng đã ẩn\" bên dưới nếu cần tìm lại/khôi phục sau này."
        )
        delete_btn.clicked.connect(self.delete_from_catalog)
        toggle_stock_btn = QPushButton("Hết hàng tạm thời / Còn hàng lại")
        toggle_stock_btn.clicked.connect(self.toggle_in_stock)
        import_btn = QPushButton("Nhập danh mục từ Excel…")
        import_btn.clicked.connect(self.import_from_excel)
        export_btn = QPushButton("Xuất danh mục ra Excel")
        export_btn.clicked.connect(self.export_excel)
        publish_btn = QPushButton("Cập nhật website giá")
        publish_btn.clicked.connect(self.publish_website)
        announce_btn = QPushButton("📢 Đăng lên kênh")
        announce_btn.clicked.connect(self.announce_to_channel)

        buttons = QHBoxLayout()
        buttons.addWidget(add_btn)
        buttons.addWidget(edit_btn)
        buttons.addWidget(toggle_btn)
        buttons.addWidget(delete_btn)
        buttons.addWidget(toggle_stock_btn)
        buttons.addWidget(import_btn)
        buttons.addStretch()
        buttons.addWidget(export_btn)
        buttons.addWidget(publish_btn)
        buttons.addWidget(announce_btn)

        self.show_hidden_check = QCheckBox("Hiện cả mặt hàng đã ẩn/ngừng bán")
        self.show_hidden_check.stateChanged.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.show_hidden_check)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        # Default to active-only: discontinued/seasonal items marked "Xóa
        # khỏi danh mục" would otherwise pile up here forever (this is the
        # one place in the app that still listed them unconditionally --
        # everywhere else already filters active=0 out, see request from
        # 25/10/2026). The checkbox lets the owner still find/restore one.
        products = list_products(self.conn, active_only=not self.show_hidden_check.isChecked())
        self.table.setRowCount(len(products))
        today = date.today().isoformat()
        for row, p in enumerate(products):
            if not p["active"]:
                status = "Ngừng bán"
            elif not p["in_stock"]:
                status = "Tạm hết hàng"
            elif p["sale_until"] and p["sale_until"] < today:
                status = "Hết hạn bán (web đã tự ẩn)"
            else:
                status = "Còn hàng"
            values = [
                p["code"],
                p["name"],
                p["unit"] or "",
                p["category"] or "",
                f"{p['cost_price']:.2f}",
                f"{p['bulk_qty']:g}" if p["bulk_qty"] else "",
                p["sale_until"] or "",
                status,
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def _selected_code(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).text()

    def _apply_dialog_image(self, dialog: ProductDialog, code: str) -> None:
        """Save/clear the product's photo after the product row itself
        is saved (apply_local_image needs the code to already exist for
        images/manifest.json's bookkeeping to make sense). Only touches
        anything if the user actually picked a new photo or explicitly
        cleared one this time."""
        picked = dialog.picked_image_path()
        if picked is not None:
            try:
                apply_local_image(self.conn, code, picked)
            except LocalImageError as exc:
                QMessageBox.warning(self, "Không lưu được ảnh", str(exc))
        elif dialog.image_removed():
            set_image_filename(self.conn, code, None)

    def add_product(self):
        dialog = ProductDialog(self, categories=list_categories(self.conn))
        if dialog.exec():
            values = dialog.values()
            if not values["code"] or not values["name"]:
                QMessageBox.warning(self, "Thiếu thông tin", "Cần nhập mã hàng và tên mặt hàng.")
                return
            if get_product(self.conn, values["code"]) is not None:
                QMessageBox.warning(self, "Mã hàng đã tồn tại", f"Mã '{values['code']}' đã có trong danh mục. Chọn 'Sửa' để thay đổi mặt hàng đó.")
                return
            upsert_product(self.conn, **values)
            set_sale_until(self.conn, values["code"], dialog.sale_until_value())
            self._apply_dialog_image(dialog, values["code"])
            self.refresh()

    def edit_product(self):
        code = self._selected_code()
        if code is None:
            return
        product = get_product(self.conn, code)
        dialog = ProductDialog(self, product=product, categories=list_categories(self.conn))
        if dialog.exec():
            values = dialog.values()
            values["code"] = code  # code can't be changed in this dialog
            # Preserve the fields this dialog doesn't expose, so saving an
            # edit never silently reactivates a discontinued product or
            # clears a "tạm hết hàng" flag.
            values["active"] = product["active"]
            values["in_stock"] = product["in_stock"]
            upsert_product(self.conn, **values)
            set_sale_until(self.conn, code, dialog.sale_until_value())
            self._apply_dialog_image(dialog, code)
            self.refresh()

    def toggle_active(self):
        code = self._selected_code()
        if code is None:
            return
        product = get_product(self.conn, code)
        set_active(self.conn, code, not product["active"])
        self.refresh()

    def delete_from_catalog(self):
        code = self._selected_code()
        if code is None:
            return
        product = get_product(self.conn, code)
        if not product["active"]:
            QMessageBox.information(self, "Đã ẩn rồi", f'Mặt hàng "{product["name"]}" đã ẩn khỏi danh mục từ trước.')
            return
        confirm = QMessageBox.question(
            self,
            "Xóa khỏi danh mục",
            f'Ẩn hoàn toàn "{product["name"]}" khỏi app và website?\n\n'
            "Dữ liệu (giá, hóa đơn cũ có mặt hàng này) vẫn được giữ nguyên, không mất gì -- "
            'chỉ không còn hiện ra khi bán/tìm kiếm nữa. Có thể khôi phục lại sau bằng cách '
            'tích "Hiện cả mặt hàng đã ẩn/ngừng bán" rồi bấm "Ngừng bán / Mở bán lại".\n\n'
            'Lưu ý: website chỉ cập nhật thật sau khi bạn bấm "Cập nhật website giá" -- '
            "trước đó khách vẫn thấy mặt hàng này trên web như cũ.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        set_active(self.conn, code, False)
        self.refresh()

    def toggle_in_stock(self):
        code = self._selected_code()
        if code is None:
            return
        product = get_product(self.conn, code)
        set_in_stock(self.conn, code, not product["in_stock"])
        self.refresh()

    def import_from_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Nhập danh mục từ Excel", "", "Excel (*.xlsx)")
        if not path:
            return
        from pathlib import Path

        try:
            written, skipped = import_catalog(self.conn, Path(path))
        except Exception as exc:  # bad file, wrong sheet name, etc.
            QMessageBox.critical(self, "Nhập thất bại", str(exc))
            return
        self.refresh()
        QMessageBox.information(
            self,
            "Đã nhập danh mục",
            f"Thêm mới {written} mặt hàng, bỏ qua {skipped} mặt hàng đã có sẵn "
            "(không ghi đè giá đã sửa trong app).",
        )

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "Xuất danh mục ra Excel", "danh-muc-hang.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        from pathlib import Path

        export_catalog(self.conn, Path(path))
        QMessageBox.information(self, "Đã xuất", f"Đã lưu danh mục vào:\n{path}")

    def publish_website(self):
        try:
            message = publish_site()
        except Exception as exc:  # subprocess/git failures, etc. — surface instead of crashing the app
            QMessageBox.critical(self, "Publish thất bại", str(exc))
            return
        QMessageBox.information(self, "Website giá", message)

    def announce_to_channel(self):
        code = self._selected_code()
        if code is None:
            return
        product = get_product(self.conn, code)
        if not product.get("sale_until"):
            confirm = QMessageBox.question(
                self,
                "Không phải hàng theo mùa",
                "Mặt hàng này chưa đặt \"Bán đến hết ngày\". Vẫn đăng lên kênh?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        already_note = ""
        if product.get("channel_announced_at"):
            already_note = f'\n\n⚠️ Mặt hàng này ĐÃ đăng lên kênh lúc {product["channel_announced_at"]} -- đăng lại sẽ ra 1 tin MỚI (không thay thế tin cũ), kiểm tra kênh trước nếu không chắc có cần đăng lại không.'
        confirm = QMessageBox.question(
            self,
            "Đăng lên kênh",
            f'Đăng "{product["name"]}" lên kênh Telegram ngay bây giờ?\n\n'
            'Nhớ bấm "Cập nhật website giá" trước nếu đây là sản phẩm mới, '
            "để khách bấm link trong tin nhắn đặt được hàng ngay (ảnh được gửi kèm trực tiếp, "
            "không phụ thuộc website)." + already_note,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        worker_url, sync_secret = bot_sync_settings()
        try:
            announce_product(self.conn, code, worker_url, sync_secret, site_repo_dir() / "images")
        except AnnounceError as exc:
            QMessageBox.critical(self, "Đăng lên kênh thất bại", str(exc))
            return
        self.refresh()
        QMessageBox.information(self, "Đã đăng lên kênh", "Tin đã gửi tới kênh Telegram.")
