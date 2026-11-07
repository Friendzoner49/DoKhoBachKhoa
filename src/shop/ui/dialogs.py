"""Small input dialogs shared by the pages. Qt-only; talks to shop.core
through the connection each page already has, never imports sqlite
details itself beyond what core functions need."""
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from shop.core.pricing import PUBLIC_MARKUP_PCT, effective_bulk_price, unit_price
from shop.core.products import gallery_list
from shop.paths import site_repo_dir

# Nhóm hàng chưa có mặt hàng nào vẫn phải hiện trong combo (lần 19,
# request #5) -- list_categories() chỉ trả nhóm ĐANG dùng, nên "Quà
# tặng" (vd Beluga vodka, lần 38) sẽ không tự xuất hiện nếu không liệt
# kê tay ở đây. Thêm nhóm mới vào đây khi cần chuẩn bị trước, không cần
# tạo sản phẩm giả.
_KNOWN_EMPTY_CATEGORIES = ["Quà tặng"]


def _ok_cancel(dialog, on_accept) -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(on_accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


class ProductDialog(QDialog):
    """Add or edit a product. Pass `product` (a dict from shop.core.products)
    to edit; omit it to add a new one. `categories` is the list of
    distinct categories already in use (shop.core.products.list_categories),
    offered as an editable combo so the website's category grouping stays
    consistent instead of drifting into near-duplicate spellings."""

    def __init__(self, parent=None, product: dict | None = None, categories: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sửa mặt hàng" if product else "Thêm mặt hàng")
        self.editing = product is not None

        self.code_edit = QLineEdit(product["code"] if product else "")
        self.code_edit.setEnabled(not self.editing)  # code is the primary key
        self.name_edit = QLineEdit(product["name"] if product else "")
        self.unit_edit = QLineEdit(product["unit"] if product else "")
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItem("")  # blank = "Khác" on the website
        all_categories = list(categories or [])
        for extra in _KNOWN_EMPTY_CATEGORIES:
            if extra not in all_categories:
                all_categories.append(extra)
        self.category_combo.addItems(all_categories)
        if product and product.get("category"):
            if self.category_combo.findText(product["category"]) < 0:
                self.category_combo.addItem(product["category"])
            self.category_combo.setCurrentText(product["category"])
        self.cost_spin = QDoubleSpinBox()
        self.cost_spin.setRange(0, 10_000_000)
        self.cost_spin.setDecimals(6)  # some costs are per-kg fractions, e.g. 277.777...
        self.cost_spin.setSuffix(" RUB")
        self.cost_spin.setValue(product["cost_price"] if product else 0)
        self.bulk_qty_spin = QDoubleSpinBox()
        self.bulk_qty_spin.setRange(0, 100_000)
        self.bulk_qty_spin.setDecimals(2)
        self.bulk_qty_spin.setValue(product["bulk_qty"] if product else 0)
        # Tên đơn vị đóng gói lớn (lần 36) -- CHỈ để ghép thành dòng văn
        # bản gửi NCC ở "Cần nhập hàng gì?" (vd "thùng" cho mì 30 gói/thùng,
        # "túi" cho gạo 4,5kg/túi). KHÔNG dùng để tính giá -- bulk_qty vẫn
        # là con số duy nhất pricing.bulk_discount() dùng.
        self.bulk_unit_edit = QLineEdit(product.get("bulk_unit", "") if product else "")
        self.bulk_unit_edit.setPlaceholderText("vd: thùng, túi, bao, kiện...")
        # Tên tiếng Nga chính thức của mặt hàng (request 03/11/2026) -- để
        # đối chiếu với "Tên tiếng Nga (AI đọc)" của từng dòng hóa đơn NCC
        # khi hàng về. Mặc định rỗng, điền dần qua các đợt -- KHÔNG BAO GIỜ
        # xuất ra website (xem shop.tools.export_public.build_payload).
        self.name_ru_edit = QLineEdit(product.get("name_ru", "") if product else "")
        self.name_ru_edit.setPlaceholderText("Chỉ hiện trong app -- không bao giờ lên website")

        # Mô tả chi tiết (lần 38, "Quà tặng") -- chỉ dành cho mặt hàng
        # cần giới thiệu dài hơn 1 dòng tên (vd rượu quà tặng). Rỗng =
        # không hiện khối mô tả trên website/app, không ảnh hưởng 146
        # mặt hàng tạp hóa thường.
        self.description_edit = QPlainTextEdit(product.get("description", "") if product else "")
        self.description_edit.setPlaceholderText(
            "Chỉ cần cho mặt hàng đặc biệt (vd quà tặng) -- để trống nếu không cần giới thiệu dài."
        )
        self.description_edit.setFixedHeight(84)

        # Image: a new file picked this session (self._picked_path, None
        # until the user chooses one -- the dialog only previews it, the
        # actual resize/save/manifest update happens after Ok, once the
        # caller knows the row exists -- see products_page.py) and a
        # "remove the current photo" flag, kept as two separate pieces of
        # state so "picked a new one" and "explicitly cleared it" can't
        # be confused with "didn't touch the image at all".
        self._picked_path: Path | None = None
        self._remove_image = False
        self._existing_image_filename = product.get("image_filename") if product else None

        self.image_preview = QLabel("Chưa có ảnh")
        self.image_preview.setFixedSize(168, 168)  # 140x140 * 1.2 (request #3, lần 19)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet("border: 1px solid palette(mid);")
        if self._existing_image_filename:
            self._show_preview(site_repo_dir() / "images" / self._existing_image_filename)

        # Seasonal/limited-time products (lần 21, request: mặt hàng theo
        # mùa mở bán giới hạn 3-5 ngày) -- sale_until is managed via its
        # own setter (shop.core.products.set_sale_until), not through
        # upsert_product's values(), so there's no "None means keep"
        # ambiguity: whatever this checkbox+date show when Ok is pressed
        # IS the new state, every time.
        self.seasonal_check = QCheckBox("Sản phẩm theo mùa (có hạn bán)")
        self.seasonal_check.toggled.connect(self._on_seasonal_toggled)
        self.sale_until_edit = QDateEdit()
        self.sale_until_edit.setCalendarPopup(True)
        self.sale_until_edit.setDisplayFormat("yyyy-MM-dd")
        existing_sale_until = product.get("sale_until") if product else None
        if existing_sale_until:
            self.seasonal_check.setChecked(True)
            self.sale_until_edit.setDate(QDate.fromString(existing_sale_until, "yyyy-MM-dd"))
        else:
            self.sale_until_edit.setDate(QDate.currentDate().addDays(4))
            self.sale_until_edit.setEnabled(False)
        seasonal_row = QHBoxLayout()
        seasonal_row.addWidget(self.seasonal_check)
        seasonal_row.addWidget(self.sale_until_edit)
        seasonal_row.addStretch()

        pick_image_btn = QPushButton("Chọn ảnh từ máy…")
        pick_image_btn.clicked.connect(self._pick_image)
        remove_image_btn = QPushButton("Xóa ảnh")
        remove_image_btn.clicked.connect(self._on_remove_image)
        image_buttons = QVBoxLayout()
        image_buttons.addWidget(pick_image_btn)
        image_buttons.addWidget(remove_image_btn)
        image_buttons.addStretch()
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_preview)
        image_row.addLayout(image_buttons)
        image_row.addStretch()

        # Bộ sưu tập ảnh (lần 38, "Quà tặng") -- NHIỀU ảnh/góc chụp cho 1
        # mặt hàng, khác với "Ảnh sản phẩm" phía trên (1 ảnh đại diện,
        # dùng cho thẻ sản phẩm/đăng kênh). Thêm/xóa chỉ thật sự ghi vào
        # images/ + products.gallery_filenames SAU khi mã hàng đã tồn tại
        # (giống hệt lý do image_row hoãn ghi -- xem _apply_dialog_image),
        # nên ở đây chỉ gom lại "sẽ thêm"/"sẽ xóa", caller áp dụng sau Ok.
        self._gallery_existing: list[str] = gallery_list(product) if product else []
        self._gallery_pending_add: list[Path] = []
        self._gallery_pending_remove: list[str] = []

        self.gallery_list_widget = QListWidget()
        self.gallery_list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery_list_widget.setIconSize(QSize(72, 72))
        self.gallery_list_widget.setFixedHeight(100)
        self.gallery_list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._refresh_gallery_widget()

        gallery_add_btn = QPushButton("Thêm ảnh vào bộ sưu tập…")
        gallery_add_btn.setToolTip("Chọn nhiều ảnh cùng lúc -- khách xem được hết các góc chụp khi bấm vào mặt hàng.")
        gallery_add_btn.clicked.connect(self._pick_gallery_images)
        gallery_remove_btn = QPushButton("Xóa ảnh đã chọn")
        gallery_remove_btn.clicked.connect(self._remove_selected_gallery_image)
        gallery_buttons = QHBoxLayout()
        gallery_buttons.addWidget(gallery_add_btn)
        gallery_buttons.addWidget(gallery_remove_btn)
        gallery_buttons.addStretch()

        form = QFormLayout()
        form.addRow("Mã hàng:", self.code_edit)
        form.addRow("Tên mặt hàng:", self.name_edit)
        form.addRow("Đơn vị:", self.unit_edit)
        form.addRow("Nhóm hàng (website):", self.category_combo)
        form.addRow("Giá vốn:", self.cost_spin)
        form.addRow("Số lượng sỉ (0 = không có):", self.bulk_qty_spin)
        # Giá sỉ ngoại lệ: mặc định giá sỉ = công thức (giá bán × số lượng sỉ × 0,98).
        # Muốn giá khác cho riêng mặt hàng này thì tích "Thêm ngoại lệ" và gõ giá BÁN
        # cả bao/thùng (cố định, mọi khách như nhau, không nhân markup riêng).
        self.bulk_override_check = QCheckBox("Thêm ngoại lệ giá sỉ (giá bán cả bao/thùng)")
        self.bulk_override_check.setChecked(bool(product and product.get("bulk_price_override")))
        self.bulk_override_spin = QSpinBox()
        self.bulk_override_spin.setRange(1, 10_000_000)
        self.bulk_override_spin.setSuffix(" RUB / cả bao")
        self.bulk_override_spin.setValue(int(product["bulk_price_override"]) if product and product.get("bulk_price_override") else 1)
        self.bulk_override_hint = QLabel()
        self.bulk_override_hint.setWordWrap(True)
        for signal in (
            self.bulk_override_check.toggled,
            self.bulk_override_spin.valueChanged,
            self.bulk_qty_spin.valueChanged,
            self.cost_spin.valueChanged,
        ):
            signal.connect(self._refresh_bulk_override)
        self.bulk_override_check.toggled.connect(self._prefill_bulk_override)
        form.addRow("", self.bulk_override_check)
        form.addRow("Giá sỉ ngoại lệ:", self.bulk_override_spin)
        form.addRow("", self.bulk_override_hint)
        self._refresh_bulk_override()
        form.addRow("Tên đơn vị đóng gói lớn:", self.bulk_unit_edit)
        form.addRow("Tên tiếng Nga:", self.name_ru_edit)
        form.addRow("Mô tả chi tiết:", self.description_edit)
        form.addRow("Ảnh sản phẩm:", image_row)
        form.addRow("Bộ sưu tập ảnh:", self.gallery_list_widget)
        form.addRow("", gallery_buttons)
        form.addRow("Bán đến hết ngày:", seasonal_row)

        buttons = _ok_cancel(self, self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _show_preview(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        self.image_preview.setPixmap(
            pixmap.scaled(168, 168, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def _pick_image(self) -> None:
        from shop.core.product_images import MIN_SHORT_SIDE

        path_str, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh sản phẩm", "", "Ảnh (*.jpg *.jpeg *.png *.webp)")
        if not path_str:
            return
        pixmap = QPixmap(path_str)
        if pixmap.isNull():
            QMessageBox.warning(self, "Ảnh không hợp lệ", "Không đọc được file này -- thử chọn file ảnh khác.")
            return
        if min(pixmap.width(), pixmap.height()) < MIN_SHORT_SIDE:
            QMessageBox.warning(
                self,
                "Ảnh quá nhỏ",
                f"Ảnh {pixmap.width()}x{pixmap.height()}px -- cạnh ngắn cần tối thiểu {MIN_SHORT_SIDE}px để hiển thị rõ trên website.",
            )
            return
        self._picked_path = Path(path_str)
        self._remove_image = False
        self._show_preview(self._picked_path)

    def _on_remove_image(self) -> None:
        self._picked_path = None
        self._remove_image = True
        self.image_preview.setPixmap(QPixmap())
        self.image_preview.setText("Chưa có ảnh")

    def _refresh_gallery_widget(self) -> None:
        self.gallery_list_widget.clear()
        images_dir = site_repo_dir() / "images"
        for filename in self._gallery_existing:
            if filename in self._gallery_pending_remove:
                continue
            item = QListWidgetItem(QIcon(str(images_dir / filename)), "")
            item.setData(Qt.ItemDataRole.UserRole, ("existing", filename))
            item.setToolTip(filename)
            self.gallery_list_widget.addItem(item)
        for path in self._gallery_pending_add:
            item = QListWidgetItem(QIcon(str(path)), "(mới)")
            item.setData(Qt.ItemDataRole.UserRole, ("new", path))
            item.setToolTip(f"{path.name} -- sẽ lưu khi bấm OK")
            self.gallery_list_widget.addItem(item)

    def _pick_gallery_images(self) -> None:
        from shop.core.product_images import MIN_SHORT_SIDE

        paths, _ = QFileDialog.getOpenFileNames(self, "Thêm ảnh vào bộ sưu tập", "", "Ảnh (*.jpg *.jpeg *.png *.webp)")
        if not paths:
            return
        rejected = []
        for path_str in paths:
            pixmap = QPixmap(path_str)
            if pixmap.isNull() or min(pixmap.width(), pixmap.height()) < MIN_SHORT_SIDE:
                rejected.append(Path(path_str).name)
                continue
            self._gallery_pending_add.append(Path(path_str))
        self._refresh_gallery_widget()
        if rejected:
            QMessageBox.warning(
                self,
                "Một số ảnh không hợp lệ",
                "Bỏ qua (ảnh hỏng hoặc quá nhỏ, cạnh ngắn cần tối thiểu "
                f"{MIN_SHORT_SIDE}px):\n" + "\n".join(rejected),
            )

    def _remove_selected_gallery_image(self) -> None:
        item = self.gallery_list_widget.currentItem()
        if item is None:
            return
        kind, value = item.data(Qt.ItemDataRole.UserRole)
        if kind == "existing":
            self._gallery_pending_remove.append(value)
        else:
            self._gallery_pending_add.remove(value)
        self._refresh_gallery_widget()

    def _on_seasonal_toggled(self, checked: bool) -> None:
        self.sale_until_edit.setEnabled(checked)

    def sale_until_value(self) -> str | None:
        if not self.seasonal_check.isChecked():
            return None
        return self.sale_until_edit.date().toString("yyyy-MM-dd")

    def picked_image_path(self) -> Path | None:
        """A new local file chosen this session, to be validated/resized/
        saved by shop.ui.local_image.apply_local_image after the product
        row itself is saved. None if the user didn't pick a new photo."""
        return self._picked_path

    def image_removed(self) -> bool:
        """True only if the user explicitly clicked "Xóa ảnh" -- distinct
        from simply not touching the image this time."""
        return self._remove_image

    def description_value(self) -> str:
        return self.description_edit.toPlainText().strip()

    def gallery_additions(self) -> list[Path]:
        """Local files picked this session, not yet resized/saved --
        applied by the caller (shop.ui.products_page) after the product
        row exists, same reasoning as picked_image_path()."""
        return list(self._gallery_pending_add)

    def _refresh_bulk_override(self, *_args):
        bulk_qty = self.bulk_qty_spin.value()
        usable = bulk_qty > 0
        self.bulk_override_check.setEnabled(usable)
        self.bulk_override_spin.setEnabled(usable and self.bulk_override_check.isChecked())
        if not usable:
            self.bulk_override_hint.setText("Cần nhập Số lượng sỉ trước thì mới đặt được giá sỉ riêng.")
            return
        price = unit_price(self.cost_spin.value(), PUBLIC_MARKUP_PCT)
        formula = effective_bulk_price(price, bulk_qty)
        text = f"Theo công thức (giá web {PUBLIC_MARKUP_PCT}%): {formula:,} RUB cả bao/thùng.".replace(",", ".")
        if self.bulk_override_check.isChecked():
            cost_total = self.cost_spin.value() * bulk_qty
            if self.bulk_override_spin.value() < cost_total:
                text += f" ⚠ Giá ngoại lệ đang THẤP HƠN giá vốn cả bao ({cost_total:,.0f} RUB) — bán lỗ.".replace(",", ".")
            if self.bulk_override_spin.value() > price * bulk_qty:
                text += " Lưu ý: cao hơn giá lẻ × số lượng nên thực tế vẫn tính theo giá lẻ."
        self.bulk_override_hint.setText(text)

    def _prefill_bulk_override(self, checked: bool):
        """Ticking "Thêm ngoại lệ" starts from the formula's price, never from a
        meaningless 1 RUB that one stray OK click could save."""
        if checked and self.bulk_qty_spin.value() > 0 and self.bulk_override_spin.value() <= 1:
            price = unit_price(self.cost_spin.value(), PUBLIC_MARKUP_PCT)
            self.bulk_override_spin.setValue(max(1, effective_bulk_price(price, self.bulk_qty_spin.value())))

    def accept(self):
        value = self.bulk_override_value()
        cost_total = self.cost_spin.value() * self.bulk_qty_spin.value()
        if value is not None and value < cost_total:
            message = (
                f"Giá sỉ ngoại lệ {value:,} RUB thấp hơn giá vốn cả bao/thùng ({cost_total:,.0f} RUB) — bán lỗ.\n\n"
                "Vẫn lưu?"
            ).replace(",", ".")
            answer = QMessageBox.question(self, "Giá sỉ thấp hơn giá vốn", message)
            if answer != QMessageBox.StandardButton.Yes:
                return
        super().accept()

    def bulk_override_value(self) -> int | None:
        """The fixed whole-bag sale price the owner typed, or None (= use the formula)."""
        if self.bulk_qty_spin.value() > 0 and self.bulk_override_check.isChecked():
            return self.bulk_override_spin.value()
        return None

    def gallery_removals(self) -> list[str]:
        """Existing gallery filenames marked for removal this session."""
        return list(self._gallery_pending_remove)

    def values(self) -> dict:
        return {
            "code": self.code_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "unit": self.unit_edit.text().strip() or None,
            "category": self.category_combo.currentText().strip() or None,
            "cost_price": self.cost_spin.value(),
            "bulk_qty": self.bulk_qty_spin.value(),
            "bulk_unit": self.bulk_unit_edit.text().strip(),
            "name_ru": self.name_ru_edit.text().strip(),
        }


class CustomerDialog(QDialog):
    def __init__(self, parent=None, customer: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sửa khách hàng" if customer else "Thêm khách hàng")

        self.name_edit = QLineEdit(customer["name"] if customer else "")
        self.address_edit = QLineEdit(customer.get("address") or "" if customer else "")
        self.contact_edit = QLineEdit(customer.get("contact") or "" if customer else "")
        self.markup_spin = QDoubleSpinBox()
        self.markup_spin.setRange(-100, 1000)
        self.markup_spin.setDecimals(2)
        self.markup_spin.setSuffix(" %")
        self.markup_spin.setValue(customer["default_markup_pct"] if customer else 7)
        self.opening_balance_spin = QDoubleSpinBox()
        self.opening_balance_spin.setRange(-100_000_000, 100_000_000)
        self.opening_balance_spin.setDecimals(0)
        self.opening_balance_spin.setSuffix(" RUB")
        self.opening_balance_spin.setValue(customer["opening_balance"] if customer else 0)

        form = QFormLayout()
        form.addRow("Tên khách hàng:", self.name_edit)
        form.addRow("Địa chỉ:", self.address_edit)
        form.addRow("Liên hệ (SĐT/Telegram):", self.contact_edit)
        form.addRow("% markup mặc định:", self.markup_spin)
        self.internal_check = QCheckBox("Dùng nội bộ (chính tôi): giá gốc, không tính công nợ/lợi nhuận")
        self.internal_check.setChecked(bool(customer and customer.get("internal")))
        self.internal_check.toggled.connect(self._on_internal_toggled)
        form.addRow("", self.internal_check)
        self._on_internal_toggled(self.internal_check.isChecked())
        form.addRow("Công nợ đầu kỳ:", self.opening_balance_spin)

        buttons = _ok_cancel(self, self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_internal_toggled(self, checked: bool):
        # Internal use = cost price: markup 0 flows into every invoice
        # (invoice editor, online-order conversion) with no other change.
        if checked:
            self.markup_spin.setValue(0)
        self.markup_spin.setEnabled(not checked)

    def values(self) -> dict:
        return {
            "internal": int(self.internal_check.isChecked()),
            "name": self.name_edit.text().strip(),
            "address": self.address_edit.text().strip() or None,
            "contact": self.contact_edit.text().strip() or None,
            "default_markup_pct": self.markup_spin.value(),
            "opening_balance": int(self.opening_balance_spin.value()),
        }


class PaymentDialog(QDialog):
    def __init__(self, parent=None, unpaid: list[dict] | None = None, debt: int | None = None):
        """`unpaid` = shop.core.summary.unpaid_invoices(): tick the invoices the customer
        is paying and the amount fills itself in (no odd numbers to type)."""
        super().__init__(parent)
        self.setWindowTitle("Ghi nhận thanh toán")
        self._unpaid = unpaid or []
        self._debt = debt

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0, 100_000_000)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSuffix(" RUB")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.note_edit = QLineEdit()

        form = QFormLayout()
        form.addRow("Số tiền:", self.amount_spin)
        form.addRow("Ngày:", self.date_edit)
        form.addRow("Ghi chú:", self.note_edit)

        buttons = _ok_cancel(self, self.accept)

        layout = QVBoxLayout(self)
        if self._unpaid:
            layout.addWidget(QLabel("Khách trả cho hóa đơn nào? Tích chọn — số tiền tự điền:"))
            self.invoice_list = QListWidget()
            for u in self._unpaid:
                text = f"#{u['id']} · {u['invoice_date']} · còn {u['remaining']:,} ₽".replace(",", ".")
                if u["remaining"] != u["total"]:
                    text += f" (hóa đơn {u['total']:,} ₽, đã trả một phần)".replace(",", ".")
                item = QListWidgetItem(text)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setData(Qt.ItemDataRole.UserRole, (u["id"], u["remaining"]))
                self.invoice_list.addItem(item)
            self.invoice_list.itemChanged.connect(self._on_invoice_ticked)
            layout.addWidget(self.invoice_list)
        if self._debt:
            pay_all_btn = QPushButton(f"Trả hết công nợ ({self._debt:,} ₽)".replace(",", "."))
            pay_all_btn.clicked.connect(lambda: self.amount_spin.setValue(self._debt))
            layout.addWidget(pay_all_btn)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_invoice_ticked(self, _item):
        ticked = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in (self.invoice_list.item(i) for i in range(self.invoice_list.count()))
            if item.checkState() == Qt.CheckState.Checked
        ]
        self.amount_spin.setValue(sum(remaining for _id, remaining in ticked))
        if ticked:
            self.note_edit.setText("Thanh toán hóa đơn " + ", ".join(f"#{invoice_id}" for invoice_id, _r in ticked))
        elif self.note_edit.text().startswith("Thanh toán hóa đơn "):
            self.note_edit.clear()

    def values(self) -> dict:
        return {
            "amount": int(self.amount_spin.value()),
            "paid_at": self.date_edit.date().toString("yyyy-MM-dd"),
            "note": self.note_edit.text().strip() or None,
        }


class PaymentsListDialog(QDialog):
    """View and delete a customer's recorded payments."""

    def __init__(self, parent, conn, customer_id: int, customer_name: str):
        super().__init__(parent)
        self.conn = conn
        self.customer_id = customer_id
        self.setWindowTitle(f"Lịch sử thanh toán — {customer_name}")
        self.resize(504, 480)  # 420x400 * 1.2 (request #3, lần 19)

        self.list_widget = QListWidget()
        delete_btn = QPushButton("Xóa khoản thanh toán đã chọn")
        delete_btn.clicked.connect(self._delete_selected)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(delete_btn)
        buttons.addStretch()
        buttons.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addLayout(buttons)

        self.refresh()

    def refresh(self):
        from shop.core.payments import list_payments

        self.list_widget.clear()
        self._payments = list_payments(self.conn, self.customer_id)
        for p in self._payments:
            text = f"{p['paid_at']}  —  {p['amount']:,} RUB".replace(",", ".")
            if p["note"]:
                text += f"  ({p['note']})"
            item = QListWidgetItem(text)
            item.setData(256, p["id"])
            self.list_widget.addItem(item)

    def _delete_selected(self):
        from shop.core.payments import delete_payment

        item = self.list_widget.currentItem()
        if item is None:
            return
        confirm = QMessageBox.question(self, "Xóa thanh toán", "Xóa khoản thanh toán này? Công nợ sẽ tăng lại tương ứng.")
        if confirm == QMessageBox.StandardButton.Yes:
            delete_payment(self.conn, item.data(256))
            self.refresh()


class ProductPickerDialog(QDialog):
    """Search-and-pick a product by name or code, for adding an invoice line."""

    def __init__(self, parent, products: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Chọn mặt hàng")
        self.resize(504, 576)  # 420x480 * 1.2 (request #3, lần 19)
        self._products = products
        self.selected_code: str | None = None

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Gõ để tìm theo tên hoặc mã...")
        self.search_edit.textChanged.connect(self._refilter)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._pick)

        buttons = _ok_cancel(self, self._confirm)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.list_widget)
        layout.addWidget(buttons)

        self._refilter("")

    def _refilter(self, text: str):
        text = text.strip().lower()
        self.list_widget.clear()
        for p in self._products:
            if text and text not in p["name"].lower() and text not in p["code"].lower():
                continue
            item = QListWidgetItem(f"{p['code']} — {p['name']} ({p['cost_price']:.0f} RUB vốn)")
            item.setData(256, p["code"])  # Qt.UserRole == 256
            self.list_widget.addItem(item)

    def _pick(self, item: QListWidgetItem):
        self.selected_code = item.data(256)
        self.accept()

    def _confirm(self):
        item = self.list_widget.currentItem()
        if item is not None:
            self.selected_code = item.data(256)
        self.accept()


class BotSyncSettingsDialog(QDialog):
    """Worker URL + Mã đồng bộ (SYNC_SECRET) for pulling online orders
    from the bot -- see shop.core.online_orders.sync_from_bot and
    bot/README.md's "Cài secret để app máy tính đồng bộ đơn hàng online"."""

    def __init__(self, parent=None, worker_url: str = "", sync_secret: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt đồng bộ đơn hàng online")

        self.url_edit = QLineEdit(worker_url)
        self.url_edit.setPlaceholderText("https://705bot-telegram.<ten-ban>.workers.dev")
        self.secret_edit = QLineEdit(sync_secret)
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout()
        form.addRow("Worker URL:", self.url_edit)
        form.addRow("Mã đồng bộ (SYNC_SECRET):", self.secret_edit)

        note = QLabel(
            "Lấy 2 giá trị này từ lúc cài đặt bot (bot/README.md, bước 7 và 10).\n"
            "Chỉ cần nhập 1 lần, app tự nhớ cho lần sau."
        )
        note.setWordWrap(True)

        buttons = _ok_cancel(self, self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str]:
        return self.url_edit.text().strip(), self.secret_edit.text().strip()


class CustomerPickerDialog(QDialog):
    """Search-and-pick an existing customer, or create a new one on the
    spot -- used when converting an online order to a real invoice,
    pre-filled with the name/phone Telegram gave for that order."""

    def __init__(self, parent, conn, customers: list[dict], suggested_name: str = "", suggested_phone: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Chọn khách hàng")
        self.resize(504, 576)  # 420x480 * 1.2 (request #3, lần 19)
        self.conn = conn
        self._customers = customers
        self._suggested_name = suggested_name
        self._suggested_phone = suggested_phone
        self.selected_customer_id: int | None = None

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Gõ để tìm theo tên...")
        self.search_edit.textChanged.connect(self._refilter)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._pick)

        new_btn = QPushButton("+ Tạo khách hàng mới…")
        new_btn.clicked.connect(self._create_new)

        buttons = _ok_cancel(self, self._confirm)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.list_widget)
        layout.addWidget(new_btn)
        layout.addWidget(buttons)

        self._refilter("")

    def _refilter(self, text: str):
        text = text.strip().lower()
        self.list_widget.clear()
        for c in self._customers:
            if text and text not in c["name"].lower():
                continue
            item = QListWidgetItem(c["name"])
            item.setData(256, c["id"])  # Qt.UserRole == 256
            self.list_widget.addItem(item)

    def _pick(self, item: QListWidgetItem):
        self.selected_customer_id = item.data(256)
        self.accept()

    def _confirm(self):
        item = self.list_widget.currentItem()
        if item is not None:
            self.selected_customer_id = item.data(256)
            self.accept()
        else:
            QMessageBox.information(self, "Chưa chọn khách hàng", "Hãy chọn 1 khách hàng trong danh sách, hoặc tạo mới.")

    def _create_new(self):
        from shop.core.customers import add_customer

        dialog = CustomerDialog(self)  # customer=None -> "Thêm khách hàng" title
        dialog.name_edit.setText(self._suggested_name)
        dialog.contact_edit.setText(self._suggested_phone)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            self.selected_customer_id = add_customer(self.conn, **values)
            self.accept()


class CustomLineDialog(QDialog):
    """A one-off invoice line with no catalog product behind it --
    request #4, lần 19: a service fee the owner types in by hand per
    order, with whatever price they decide (not derived from any
    cost_price/markup)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thêm phí dịch vụ")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Vd: Phí vận chuyển, phí đóng gói...")
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0, 10_000_000)
        self.price_spin.setDecimals(0)
        self.price_spin.setSuffix(" RUB")
        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setRange(0.01, 100_000)
        self.qty_spin.setDecimals(2)
        self.qty_spin.setValue(1)

        form = QFormLayout()
        form.addRow("Tên phí:", self.name_edit)
        form.addRow("Đơn giá:", self.price_spin)
        form.addRow("Số lượng:", self.qty_spin)

        buttons = _ok_cancel(self, self._confirm)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _confirm(self):
        if not self.name_edit.text().strip():
            QMessageBox.information(self, "Chưa nhập tên phí", "Gõ tên cho khoản phí này trước.")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "unit_price": int(self.price_spin.value()),
            "qty": self.qty_spin.value(),
        }


class TypedConfirmDialog(QDialog):
    """A confirmation stronger than a Yes/No QMessageBox, for the two
    actions in shop.ui.settings_page that permanently destroy real data
    (factory reset, importing a package) -- the OK button stays disabled
    until the user types the exact confirm word, so a reflexive
    double-click or Enter-key habit can't trigger it by accident."""

    def __init__(self, parent, title: str, message: str, confirm_word: str = "XOA"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(576, 0)  # 480x0 * 1.2 (request #3, lần 19)
        self._confirm_word = confirm_word

        label = QLabel(message)
        label.setWordWrap(True)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(f'Gõ "{confirm_word}" để xác nhận')
        self.edit.textChanged.connect(self._update_ok_enabled)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self.edit)
        layout.addWidget(self.buttons)

    def _update_ok_enabled(self, text: str):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(text.strip().upper() == self._confirm_word)
