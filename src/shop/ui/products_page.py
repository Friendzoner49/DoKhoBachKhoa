import sqlite3
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    deadline_passed,
    get_food_tab_always,
    get_product,
    list_expired_dishes,
    list_categories,
    list_option_groups,
    list_products,
    set_active,
    set_bulk_price_override,
    set_description,
    set_ingredients,
    set_fixed_price,
    set_food_tab_always,
    set_image_filename,
    set_in_stock,
    set_option,
    set_sale_until,
    upsert_product,
)
from shop.core.stock import remaining, set_stock_limit
from shop.core.text import normalize
from shop.excel.catalog_export import export_catalog
from shop.paths import bot_sync_settings, site_repo_dir
from shop.tools.import_xlsx import import_catalog
from shop.tools.publish_site import publish as publish_site
from shop.ui.dialogs import HideExpiredDishesDialog, ProductDialog
from shop.ui.local_image import LocalImageError, apply_gallery_photo, apply_local_image, remove_gallery_photo

HEADERS = ["Mã hàng", "Tên mặt hàng", "Đơn vị", "Nhóm hàng", "Giá vốn", "SL sỉ", "Hạn đặt", "Tình trạng"]

# 28/10/2026: the 3 states a product can actually be SET to -- "Hết hạn
# đặt (web hiện xám)" (seen in the table's "Tình trạng" column) is a 4th
# DISPLAY-only state derived from sale_until, not something picked here;
# it clears itself once sale_until passes, see ProductDialog's date field.
STATUS_DANG_BAN = "Đang bán"
STATUS_TAM_HET = "Tạm hết hàng"
STATUS_NGUNG_BAN = "Ngừng bán"


def _controllable_status(product: dict) -> str:
    """Status derived purely from active/in_stock -- ignores sale_until,
    unlike the richer per-row text in refresh()."""
    if not product["active"]:
        return STATUS_NGUNG_BAN
    if not product["in_stock"]:
        return STATUS_TAM_HET
    return STATUS_DANG_BAN


class ProductsPage(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Bấm đúp 1 dòng mở chi tiết mặt hàng (request 03/11/2026) -- để
        # kiểm thử/đối chiếu tên tiếng Nga trước khi hàng về, không cần
        # chọn dòng rồi bấm "Sửa" riêng.
        self.table.itemDoubleClicked.connect(lambda _item: self.edit_product())
        # Click a column title to sort by it, again to reverse. Sorted by hand
        # (not setSortingEnabled) so pre-order dishes always stay above grocery.
        self._sort_column, self._sort_reverse = 1, False
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_clicked)

        add_btn = QPushButton("Thêm mặt hàng")
        add_btn.clicked.connect(self.add_product)
        edit_btn = QPushButton("Sửa")
        edit_btn.clicked.connect(self.edit_product)
        # 1 ô chọn trạng thái 3 nấc thay cho 3 nút riêng trước đây
        # ("Ngừng bán / Mở bán lại" và "🗑 Xóa khỏi danh mục" làm Y HỆT
        # nhau; "Hết hàng tạm thời / Còn hàng lại" tách biệt) — vẫn 2
        # cột dữ liệu active/in_stock như cũ, chỉ gộp GIAO DIỆN.
        self.status_combo = QComboBox()
        self.status_combo.addItems([STATUS_DANG_BAN, STATUS_TAM_HET, STATUS_NGUNG_BAN])
        self.status_combo.setToolTip(
            'Chọn trạng thái rồi bấm "Áp dụng". "Ngừng bán" ẩn hoàn toàn khỏi app/website\n'
            "(không xóa dữ liệu — hóa đơn cũ không bị ảnh hưởng, khôi phục lại được bất cứ lúc nào)."
        )
        apply_status_btn = QPushButton("Áp dụng")
        apply_status_btn.clicked.connect(self.apply_status)
        self.table.itemSelectionChanged.connect(self._sync_status_combo)
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
        buttons.addWidget(self.status_combo)
        buttons.addWidget(apply_status_btn)
        buttons.addWidget(import_btn)
        buttons.addStretch()
        buttons.addWidget(export_btn)
        buttons.addWidget(publish_btn)
        buttons.addWidget(announce_btn)

        self.show_hidden_check = QCheckBox("Hiện cả mặt hàng đã ẩn/ngừng bán")
        self.show_hidden_check.stateChanged.connect(self.refresh)
        hide_expired_btn = QPushButton("Ẩn món hết hạn đặt…")
        hide_expired_btn.setToolTip("Chọn món ăn đặt trước đã qua hạn đặt để ẩn khỏi website ngay")
        hide_expired_btn.clicked.connect(self.hide_expired_dishes)
        second_row = QHBoxLayout()
        second_row.addWidget(self.show_hidden_check)
        second_row.addStretch()
        self.food_tab_check = QCheckBox('Luôn hiện tab "Món ăn đặt trước" trên web')
        self.food_tab_check.setToolTip(
            'Bỏ tick: web chỉ hiện tab "Món ăn đặt trước" khi có món.\n'
            'Tick: tab luôn hiện; chưa có món thì ghi "Hiện chưa có món nào đang nhận đặt".\n'
            'Web đổi sau khi bấm "Cập nhật website giá".'
        )
        self.food_tab_check.setChecked(get_food_tab_always(self.conn))
        self.food_tab_check.toggled.connect(self._on_food_tab_toggled)
        second_row.addWidget(self.food_tab_check)
        second_row.addWidget(hide_expired_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addLayout(second_row)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        # Default to active-only: discontinued/seasonal items marked "Xóa
        # khỏi danh mục" would otherwise pile up here forever (this is the
        # one place in the app that still listed them unconditionally --
        # everywhere else already filters active=0 out, see request from
        # 25/10/2026). The checkbox lets the owner still find/restore one.
        selected = self._selected_code()
        products = self._sorted(list_products(self.conn, active_only=not self.show_hidden_check.isChecked()))
        # Rows move when sorting/saving: drop the old position, reselect by code
        # below, so "Sửa"/"Áp dụng" can never hit a different item.
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.setRowCount(len(products))
        self.table.horizontalHeader().setSortIndicator(
            self._sort_column,
            Qt.SortOrder.DescendingOrder if self._sort_reverse else Qt.SortOrder.AscendingOrder,
        )
        # Mirrors FOOD_EXPIRED_VISIBLE_DAYS in the site template: the web keeps a
        # past-deadline dish greyed for 7 days, then drops it on its own.
        web_cutoff = (date.today() - timedelta(days=7)).isoformat()
        for row, p in enumerate(products):
            if not p["active"]:
                status = "Ngừng bán"
            elif not p["in_stock"]:
                status = "Tạm hết hàng"
            elif deadline_passed(p):
                status = "Hết hạn đặt (web hiện xám)" if p["sale_until"] >= web_cutoff else "Hết hạn đặt (web đã tự ẩn)"
            else:
                status = "Còn hàng"
            left = remaining(self.conn, p) if p["sale_until"] and status == "Còn hàng" else None
            if left is not None:
                status = f"Còn {left}/{p['stock_limit']} suất" if left else f"Hết suất (0/{p['stock_limit']})"
            values = [
                p["code"],
                p["name"],
                p["unit"] or "",
                p["category"] or "",
                f"{p['cost_price']:.2f}" + (f" (giá bán {p['fixed_price']})" if p["fixed_price"] else ""),
                (f"{p['bulk_qty']:g}" + (" (giá riêng)" if p["bulk_price_override"] else "")) if p["bulk_qty"] else "",
                " ".join(filter(None, [p["sale_until"], p["sale_until_time"]])),
                status,
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        for row, p in enumerate(products):
            if p["code"] == selected:
                self.table.selectRow(row)
                break

    def _on_header_clicked(self, column: int):
        self._sort_reverse = column == self._sort_column and not self._sort_reverse
        self._sort_column = column
        self.refresh()

    def _sorted(self, products: list[dict]) -> list[dict]:
        """Pre-order dishes first, grocery below; inside each block what is on
        sale now comes first, then the clicked column. list_products already
        gives Vietnamese name order, which stays as the tie-break."""
        keys = [
            lambda p: p["code"],
            None,  # name: the order list_products returned
            lambda p: normalize(p["unit"] or ""),
            lambda p: normalize(p["category"] or ""),
            lambda p: p["cost_price"],
            lambda p: p["bulk_qty"] or 0,
            lambda p: (p["sale_until"] or "", p["sale_until_time"] or "24"),
            lambda p: (not p["active"], not p["in_stock"], deadline_passed(p)),  # on sale first
        ]
        key = keys[self._sort_column]
        if key is None:
            ordered = products[::-1] if self._sort_reverse else list(products)
        else:
            ordered = sorted(products, key=key, reverse=self._sort_reverse)
        return sorted(ordered, key=lambda p: (not p["sale_until"], not self._on_sale(p)))

    def _on_sale(self, p: dict) -> bool:
        """A customer can order it right now (not stopped, out of stock, past
        its deadline or out of portions)."""
        return bool(p["active"] and p["in_stock"]) and not deadline_passed(p) and remaining(self.conn, p) != 0

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

    def _apply_dialog_gallery(self, dialog: ProductDialog, code: str) -> None:
        """Save/remove "Quà tặng" gallery photos after the row itself
        exists -- same deferred-apply reasoning as _apply_dialog_image."""
        for filename in dialog.gallery_removals():
            remove_gallery_photo(self.conn, code, filename)
        for path in dialog.gallery_additions():
            try:
                apply_gallery_photo(self.conn, code, path)
            except LocalImageError as exc:
                QMessageBox.warning(self, "Không lưu được ảnh", str(exc))

    def add_product(self):
        dialog = ProductDialog(
            self, categories=list_categories(self.conn), option_groups=list_option_groups(self.conn)
        )
        if dialog.exec():
            values = dialog.values()
            if not values["code"] or not values["name"]:
                QMessageBox.warning(self, "Thiếu thông tin", "Cần nhập mã hàng và tên mặt hàng.")
                return
            if get_product(self.conn, values["code"]) is not None:
                QMessageBox.warning(self, "Mã hàng đã tồn tại", f"Mã '{values['code']}' đã có trong danh mục. Chọn 'Sửa' để thay đổi mặt hàng đó.")
                return
            upsert_product(self.conn, **values)
            set_bulk_price_override(self.conn, values["code"], dialog.bulk_override_value())
            set_fixed_price(self.conn, values["code"], dialog.fixed_price_value())
            set_option(self.conn, values["code"], *dialog.option_value())
            set_sale_until(self.conn, values["code"], dialog.sale_until_value(), dialog.sale_until_time_value())
            set_stock_limit(self.conn, values["code"], dialog.stock_limit_value())
            set_description(self.conn, values["code"], dialog.description_value())
            set_ingredients(self.conn, values["code"], dialog.ingredients_value())
            self._apply_dialog_image(dialog, values["code"])
            self._apply_dialog_gallery(dialog, values["code"])
            self.refresh()

    def edit_product(self):
        code = self._selected_code()
        if code is None:
            return
        product = get_product(self.conn, code)
        dialog = ProductDialog(
            self, product=product, categories=list_categories(self.conn), option_groups=list_option_groups(self.conn)
        )
        if dialog.exec():
            values = dialog.values()
            values["code"] = code  # code can't be changed in this dialog
            # Preserve the fields this dialog doesn't expose, so saving an
            # edit never silently reactivates a discontinued product or
            # clears a "tạm hết hàng" flag.
            values["active"] = product["active"]
            values["in_stock"] = product["in_stock"]
            upsert_product(self.conn, **values)
            set_bulk_price_override(self.conn, code, dialog.bulk_override_value())
            set_fixed_price(self.conn, code, dialog.fixed_price_value())
            set_option(self.conn, code, *dialog.option_value())
            set_sale_until(self.conn, code, dialog.sale_until_value(), dialog.sale_until_time_value())
            set_stock_limit(self.conn, code, dialog.stock_limit_value(), previous=product)
            set_description(self.conn, code, dialog.description_value())
            set_ingredients(self.conn, code, dialog.ingredients_value())
            self._apply_dialog_image(dialog, code)
            self._apply_dialog_gallery(dialog, code)
            self.refresh()

    def _sync_status_combo(self):
        """Shows the SELECTED row's current status in the combo, so
        picking a different row doesn't leave a stale choice sitting
        there from the row picked before it."""
        code = self._selected_code()
        if code is None:
            return
        product = get_product(self.conn, code)
        self.status_combo.blockSignals(True)
        self.status_combo.setCurrentText(_controllable_status(product))
        self.status_combo.blockSignals(False)

    def apply_status(self):
        code = self._selected_code()
        if code is None:
            return
        product = get_product(self.conn, code)
        target = self.status_combo.currentText()
        if target == _controllable_status(product):
            return  # no change picked -- nothing to do

        if target == STATUS_NGUNG_BAN:
            confirm = QMessageBox.question(
                self,
                "Ngừng bán",
                f'Ẩn hoàn toàn "{product["name"]}" khỏi app và website?\n\n'
                "Dữ liệu (giá, hóa đơn cũ có mặt hàng này) vẫn được giữ nguyên, không mất gì -- "
                'chỉ không còn hiện ra khi bán/tìm kiếm nữa. Có thể khôi phục lại sau bằng cách '
                'tích "Hiện cả mặt hàng đã ẩn/ngừng bán" rồi chọn lại trạng thái khác.\n\n'
                'Lưu ý: website chỉ cập nhật thật sau khi bạn bấm "Cập nhật website giá" -- '
                "trước đó khách vẫn thấy mặt hàng này trên web như cũ.",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                self._sync_status_combo()
                return
            set_active(self.conn, code, False)
        elif target == STATUS_TAM_HET:
            set_active(self.conn, code, True)
            set_in_stock(self.conn, code, False)
        else:  # STATUS_DANG_BAN
            set_active(self.conn, code, True)
            set_in_stock(self.conn, code, True)
        self.refresh()

    def _on_food_tab_toggled(self, checked: bool):
        set_food_tab_always(self.conn, checked)
        QMessageBox.information(
            self,
            "Tab Món ăn đặt trước",
            ('Tab "Món ăn đặt trước" sẽ luôn hiện trên web, kể cả khi chưa có món.' if checked
             else 'Tab "Món ăn đặt trước" sẽ chỉ hiện trên web khi có món.')
            + '\n\nBấm "Cập nhật website giá" để web đổi theo.',
        )

    def hide_expired_dishes(self):
        dishes = list_expired_dishes(self.conn)
        if not dishes:
            QMessageBox.information(self, "Ẩn món hết hạn đặt", "Không có món nào đã qua hạn đặt mà chưa ẩn.")
            return
        dialog = HideExpiredDishesDialog(dishes, self)
        if dialog.exec() != HideExpiredDishesDialog.DialogCode.Accepted:
            return
        codes = dialog.checked_codes()
        if not codes:
            return
        for code in codes:
            set_active(self.conn, code, False)
        self.refresh()
        confirm = QMessageBox.question(
            self,
            "Cập nhật website?",
            f"Đã ẩn {len(codes)} món trong app.\n\n"
            "Website chỉ đổi sau khi cập nhật. Cập nhật website ngay bây giờ?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.publish_website()

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
                "Không phải món ăn đặt trước",
                "Mặt hàng này chưa đặt hạn đặt món (ô \"Món ăn đặt trước\"). Vẫn đăng lên kênh?",
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
