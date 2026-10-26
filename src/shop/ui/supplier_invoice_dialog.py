"""Import/review one supplier invoice: load a photo, optionally run OCR
as a reading aid, and build the line-item table by hand -- matching each
line to a catalog product and a unit-conversion factor before any
cost_price is touched. Nothing here is fully automatic on purpose: see
shop.core.supplier_invoices and shop.ocr.engine for why.
"""
import shutil
import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from shop.core.products import get_product
from shop.core.supplier_invoices import (
    add_line,
    apply_invoice,
    create_invoice,
    get_invoice,
    known_lines,
    line_cost_preview,
    remove_line,
    set_paid,
    suggest_matches,
    update_line,
)
from shop.ocr.engine import OCRUnavailable, ocr_image
from shop.ocr.vision import DEFAULT_MODEL, VisionOcrUnavailable, read_invoice_table
from shop.paths import supplier_invoices_dir
from shop.ui.dialogs import ProductPickerDialog

COL_NAME, COL_QTY, COL_UNIT, COL_PRICE, COL_CONV, COL_CODE, COL_OLD, COL_NEW, COL_DELTA = range(9)
HEADERS = ["Tên trên hóa đơn", "SL", "Đơn vị", "Đơn giá", "Quy đổi (vd. case=30)", "Mã hàng khớp", "Giá cũ", "Giá mới", "Δ%"]
EDITABLE_COLS = {COL_NAME, COL_QTY, COL_UNIT, COL_PRICE, COL_CONV, COL_CODE}
INCREASE_COLOR = QColor("#ffe3d1")
DECREASE_COLOR = QColor("#dbf3df")


class _MatchPickerDialog(QDialog):
    """Pick from suggest_matches()'s top candidates for one raw line, or
    fall back to a full product search if none of them is right."""

    def __init__(self, parent, matches: list[dict], all_products: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Chọn mã hàng khớp")
        self.resize(504, 384)  # 420x320 * 1.2 (request #3, lần 19)
        self.selected_code: str | None = None
        self.selected_conversion: float = 1.0
        self._all_products = all_products

        self.list_widget = QListWidget()
        for m in matches:
            label = f"{m['code']} — {m['name']}"
            if m["score"] >= 999:
                label += "  (đã dùng trước đây)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, (m["code"], m["unit_conversion"]))
            self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(self._pick)

        search_btn = QPushButton("Tìm mặt hàng khác…")
        search_btn.clicked.connect(self._search_manually)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Gợi ý (dựa trên tên đã nhập):"))
        layout.addWidget(self.list_widget)
        layout.addWidget(search_btn)
        layout.addWidget(buttons)

    def _pick(self, item: QListWidgetItem):
        self.selected_code, self.selected_conversion = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _confirm(self):
        item = self.list_widget.currentItem()
        if item is not None:
            self.selected_code, self.selected_conversion = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _search_manually(self):
        picker = ProductPickerDialog(self, self._all_products)
        if picker.exec() and picker.selected_code:
            self.selected_code = picker.selected_code
            self.selected_conversion = 1.0
            self.accept()


COL_PICK_NAME, COL_PICK_COUNT, COL_PICK_QTY = range(3)


class _KnownLinesPickerDialog(QDialog):
    """Checklist for "Thêm mặt hàng quen thuộc" (lần 22): shows every
    product ever matched on a past supplier invoice, most-recurring
    first, so the owner can TICK only what's actually on THIS delivery
    (checking the photo) and type each quantity right here -- never a
    blind "add everything", which with only one supplier would grow
    toward the whole catalog (see known_lines()' docstring)."""

    def __init__(self, parent, candidates: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Thêm mặt hàng quen thuộc")
        self.resize(600, 600)
        self._candidates = candidates

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Gõ để lọc theo tên...")
        self.search_edit.textChanged.connect(self._refilter)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Tên trên hóa đơn", "Đã mua (số đợt)", "SL đợt này"])

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tích vào những mặt hàng THỰC SỰ có trong ảnh hóa đơn đang xem, và gõ đúng số lượng của đợt này:"))
        layout.addWidget(self.search_edit)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

        self._refilter("")

    def _refilter(self, text: str):
        # Preserve any check/qty the user already set before filtering,
        # keyed by matched_code -- so typing in the search box doesn't
        # silently discard a tick made before narrowing the list.
        prior = {}
        for row in range(self.table.rowCount()):
            code = self.table.item(row, COL_PICK_NAME).data(Qt.ItemDataRole.UserRole)
            check_item = self.table.item(row, COL_PICK_NAME)
            qty_item = self.table.item(row, COL_PICK_QTY)
            prior[code] = (check_item.checkState(), qty_item.text())

        text = text.strip().lower()
        self.table.setRowCount(0)
        for c in self._candidates:
            if text and text not in (c["raw_name"] or "").lower() and text not in c["matched_code"].lower():
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QTableWidgetItem(f"{c['raw_name']} ({c['matched_code']})")
            name_item.setFlags((name_item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setData(Qt.ItemDataRole.UserRole, c["matched_code"])
            prior_check, prior_qty = prior.get(c["matched_code"], (Qt.CheckState.Unchecked, None))
            name_item.setCheckState(prior_check)
            self.table.setItem(row, COL_PICK_NAME, name_item)

            count_item = QTableWidgetItem(str(c["order_count"]))
            count_item.setFlags(count_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, COL_PICK_COUNT, count_item)

            default_qty = prior_qty if prior_qty is not None else (f"{c['raw_qty']:g}" if c["raw_qty"] is not None else "")
            self.table.setItem(row, COL_PICK_QTY, QTableWidgetItem(default_qty))
        self.table.resizeColumnsToContents()

    def selected_lines(self) -> list[dict]:
        """Only the TICKED rows, with whatever quantity is currently
        typed in (falls back to that product's own last-known qty if
        left blank)."""
        by_code = {c["matched_code"]: c for c in self._candidates}
        result = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, COL_PICK_NAME)
            if name_item.checkState() != Qt.CheckState.Checked:
                continue
            code = name_item.data(Qt.ItemDataRole.UserRole)
            source = by_code[code]
            qty_text = self.table.item(row, COL_PICK_QTY).text().strip().replace(",", ".")
            try:
                qty = float(qty_text) if qty_text else source["raw_qty"]
            except ValueError:
                qty = source["raw_qty"]
            result.append(
                {
                    "matched_code": code,
                    "raw_name": source["raw_name"],
                    "raw_qty": qty,
                    "raw_unit": source["raw_unit"],
                    "unit_conversion": source["unit_conversion"],
                }
            )
        return result


class SupplierInvoiceDialog(QDialog):
    def __init__(self, parent, conn: sqlite3.Connection, invoice_id: int | None = None):
        super().__init__(parent)
        self.conn = conn
        self._rotation = 0
        self._image_path: Path | None = None

        if invoice_id is None:
            invoice_id = create_invoice(conn, invoice_date=date.today().isoformat())
        self.invoice_id = invoice_id
        invoice = get_invoice(conn, invoice_id)

        self.setWindowTitle(f"Hóa đơn nhà cung cấp #{invoice_id}")
        self.resize(1260, 780)  # 1050x650 * 1.2 (request #3, lần 19)

        # --- left: photo + OCR assist ---
        self.image_label = QLabel("Chưa có ảnh")
        self.image_label.setFixedSize(360, 480)  # 300x400 * 1.2
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid #ccc; background: #fafafa;")

        choose_photo_btn = QPushButton("Chọn ảnh…")
        choose_photo_btn.clicked.connect(self.choose_photo)
        rotate_btn = QPushButton("Xoay 90°")
        rotate_btn.clicked.connect(self.rotate_image)
        ocr_btn = QPushButton("Đọc chữ (OCR)")
        ocr_btn.clicked.connect(self.run_ocr)
        ai_ocr_btn = QPushButton("Đọc bảng hàng (AI, chậm hơn)…")
        ai_ocr_btn.setToolTip(
            f"Dùng model AI cục bộ ({DEFAULT_MODEL} qua Ollama) để đọc cả bảng hàng hóa, không chỉ phần tiêu đề.\n"
            "Đọc tốt hơn OCR thường nhưng chậm hơn (khoảng 15-30 giây/ảnh) và cần cài Ollama riêng (xem README.md).\n"
            "Vẫn chỉ là gợi ý đọc — luôn đối chiếu với ảnh thật trước khi gõ vào bảng."
        )
        ai_ocr_btn.clicked.connect(self.run_vision_ocr)

        photo_buttons = QHBoxLayout()
        photo_buttons.addWidget(choose_photo_btn)
        photo_buttons.addWidget(rotate_btn)
        photo_buttons.addWidget(ocr_btn)
        photo_buttons.addWidget(ai_ocr_btn)

        self.ocr_text = QPlainTextEdit()
        self.ocr_text.setReadOnly(True)
        self.ocr_text.setPlaceholderText(
            "Bấm \"Đọc chữ (OCR)\" để xem văn bản máy đọc được từ ảnh, dùng để tham khảo khi gõ bảng bên phải.\n\n"
            "Lưu ý: chữ máy đọc có thể sai, nhất là số — luôn đối chiếu với ảnh thật trước khi tin.\n\n"
            "\"Đọc bảng hàng (AI)\" đọc được cả bảng hàng (OCR thường chỉ đọc được tiêu đề), nhưng cần cài "
            "Ollama riêng và chậm hơn — xem README.md."
        )

        left = QVBoxLayout()
        left.addWidget(self.image_label)
        left.addLayout(photo_buttons)
        left.addWidget(self.ocr_text)

        # --- right: header fields + line table ---
        self.number_edit = QLineEdit(invoice.get("invoice_number") or "")
        self.number_edit.editingFinished.connect(self._save_header)
        self.date_edit = QLineEdit(invoice.get("invoice_date") or "")
        self.date_edit.setPlaceholderText("YYYY-MM-DD")
        self.date_edit.editingFinished.connect(self._save_header)
        self.total_edit = QLineEdit(f"{invoice['total_amount']:g}" if invoice["total_amount"] else "")
        self.total_edit.setPlaceholderText("Tổng tiền in trên hóa đơn (để đối chiếu)")
        self.total_edit.editingFinished.connect(self._save_header)

        form = QFormLayout()
        form.addRow("Số hóa đơn:", self.number_edit)
        form.addRow("Ngày (YYYY-MM-DD):", self.date_edit)
        form.addRow("Tổng tiền trên hóa đơn:", self.total_edit)
        if invoice.get("note"):
            # Ghi chú kèm theo khi ảnh được gửi qua lệnh "/hangve" trong
            # group Telegram (lần 20) -- chỉ hiện khi có, không sửa được
            # ở đây (sửa trong Telegram, không phải trong app).
            note_label = QLabel(invoice["note"])
            note_label.setWordWrap(True)
            form.addRow("Ghi chú (Telegram):", note_label)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.itemChanged.connect(self._on_item_changed)

        add_row_btn = QPushButton("Thêm dòng")
        add_row_btn.clicked.connect(self.add_row)
        add_known_btn = QPushButton("Thêm mặt hàng quen thuộc")
        add_known_btn.setToolTip(
            "Mở danh sách mặt hàng bạn đã từng khớp mã trước đây (nhiều đợt mua nhất lên đầu).\n"
            "Tích vào đúng mặt hàng CÓ trong ảnh hóa đơn đang xem, gõ số lượng, rồi mới thêm vào bảng."
        )
        add_known_btn.clicked.connect(self.add_known_lines)
        remove_row_btn = QPushButton("Xóa dòng")
        remove_row_btn.clicked.connect(self.remove_row)
        suggest_btn = QPushButton("Gợi ý mã hàng cho dòng đang chọn")
        suggest_btn.clicked.connect(self.suggest_for_selected)

        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add_row_btn)
        row_buttons.addWidget(add_known_btn)
        row_buttons.addWidget(remove_row_btn)
        row_buttons.addWidget(suggest_btn)

        self.total_label = QLabel()
        self.total_label.setWordWrap(True)

        apply_btn = QPushButton("Áp dụng giá mới vào danh mục")
        apply_btn.clicked.connect(self.apply_changes)
        self.paid_btn = QPushButton()
        self.paid_btn.clicked.connect(self.toggle_paid)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)

        bottom_buttons = QHBoxLayout()
        bottom_buttons.addWidget(apply_btn)
        bottom_buttons.addWidget(self.paid_btn)
        bottom_buttons.addStretch()
        bottom_buttons.addWidget(close_btn)

        right = QVBoxLayout()
        right.addLayout(form)
        right.addLayout(row_buttons)
        right.addWidget(self.table)
        right.addWidget(self.total_label)
        right.addLayout(bottom_buttons)

        main = QHBoxLayout(self)
        main.addLayout(left, 1)
        main.addLayout(right, 2)

        if invoice.get("photo_filename"):
            self._image_path = supplier_invoices_dir() / invoice["photo_filename"]
            self._show_image()

        self.refresh()

    # ---- photo ----
    def choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh hóa đơn", "", "Ảnh (*.jpg *.jpeg *.png)")
        if not path:
            return
        src = Path(path)
        dest_name = f"{self.invoice_id}-{src.name}"
        dest = supplier_invoices_dir() / dest_name
        shutil.copy(src, dest)
        self.conn.execute("UPDATE supplier_invoices SET photo_filename = ? WHERE id = ?", (dest_name, self.invoice_id))
        self.conn.commit()
        self._image_path = dest
        self._rotation = 0
        self._show_image()

    def rotate_image(self):
        self._rotation = (self._rotation + 90) % 360
        self._show_image()

    def _show_image(self):
        if not self._image_path or not self._image_path.exists():
            return
        pixmap = QPixmap(str(self._image_path))
        if self._rotation:
            pixmap = pixmap.transformed(QTransform().rotate(self._rotation))
        self.image_label.setPixmap(
            pixmap.scaled(
                self.image_label.width(),
                self.image_label.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def run_ocr(self):
        if not self._image_path or not self._image_path.exists():
            QMessageBox.information(self, "Chưa có ảnh", "Chọn ảnh hóa đơn trước.")
            return
        # OCR the actual oriented photo, not just the on-screen preview --
        # written with Qt's own image classes (no Pillow): Pillow is a
        # dev-only dependency the shipped app never imports.
        pixmap = QPixmap(str(self._image_path))
        if self._rotation:
            pixmap = pixmap.transformed(QTransform().rotate(self._rotation))
        rotated_path = self._image_path.with_name(self._image_path.stem + "-rotated.png")
        pixmap.save(str(rotated_path))
        try:
            text = ocr_image(rotated_path)
        except OCRUnavailable as exc:
            self.ocr_text.setPlainText(str(exc))
            return
        self.ocr_text.setPlainText(text)

    def run_vision_ocr(self):
        if not self._image_path or not self._image_path.exists():
            QMessageBox.information(self, "Chưa có ảnh", "Chọn ảnh hóa đơn trước.")
            return
        pixmap = QPixmap(str(self._image_path))
        if self._rotation:
            pixmap = pixmap.transformed(QTransform().rotate(self._rotation))
        # A full-resolution phone photo (sent as a Telegram "File", e.g.
        # for /hangve -- see bot/README.md mục 13) can be several times
        # larger than the Telegram-compressed test photos this was tuned
        # against, and overflow read_invoice_table()'s num_ctx outright
        # (confirmed: an ~370KB test photo already used over half of an
        # 8192-token context). Downscale before sending -- this never
        # touches the saved invoice photo or the Tesseract OCR path,
        # only what gets sent to the vision model.
        VISION_MAX_SIDE = 1600
        if pixmap.width() > VISION_MAX_SIDE or pixmap.height() > VISION_MAX_SIDE:
            pixmap = pixmap.scaled(
                VISION_MAX_SIDE,
                VISION_MAX_SIDE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        rotated_path = self._image_path.with_name(self._image_path.stem + "-vision.png")
        pixmap.save(str(rotated_path))
        self.ocr_text.setPlainText("Đang đọc ảnh bằng AI… (có thể mất 15-30 giây, app sẽ không phản hồi trong lúc này)")
        QApplication.processEvents()
        # Blocking call on the UI thread, same trade-off already accepted
        # for sync_from_bot() in online_orders_page.py: no worker thread,
        # but a visible sign (wait cursor + message above) that the app
        # is busy instead of looking frozen.
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            text = read_invoice_table(rotated_path)
        except VisionOcrUnavailable as exc:
            self.ocr_text.setPlainText(str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.ocr_text.setPlainText(text)

    # ---- header ----
    def _save_header(self):
        try:
            total_amount = int(round(float(self.total_edit.text().strip().replace(",", ".") or 0)))
        except ValueError:
            total_amount = 0
        self.conn.execute(
            "UPDATE supplier_invoices SET invoice_number = ?, invoice_date = ?, total_amount = ? WHERE id = ?",
            (self.number_edit.text().strip() or None, self.date_edit.text().strip() or None, total_amount, self.invoice_id),
        )
        self.conn.commit()
        self.refresh()

    # ---- lines ----
    def refresh(self):
        self.table.blockSignals(True)
        invoice = get_invoice(self.conn, self.invoice_id)
        self._line_ids = [line["id"] for line in invoice["lines"]]
        self.table.setRowCount(len(invoice["lines"]))
        line_total_sum = 0.0
        for row, line in enumerate(invoice["lines"]):
            preview = line_cost_preview(self.conn, line)
            line_total_sum += line["raw_line_total"] or 0
            values = [
                line["raw_name"] or "",
                f"{line['raw_qty']:g}" if line["raw_qty"] is not None else "",
                line["raw_unit"] or "",
                f"{line['raw_unit_price']:g}" if line["raw_unit_price"] is not None else "",
                f"{line['unit_conversion']:g}",
                line["matched_code"] or "",
                f"{preview['old_cost']:.2f}" if preview["old_cost"] is not None else "",
                f"{preview['new_cost']:.2f}" if preview["new_cost"] is not None else "",
                f"{preview['delta_pct']:+.1f}%" if preview["delta_pct"] is not None else "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col not in EDITABLE_COLS:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)
            if preview["delta_pct"] is not None and abs(preview["delta_pct"]) >= 1:
                color = INCREASE_COLOR if preview["delta_pct"] > 0 else DECREASE_COLOR
                for col in (COL_OLD, COL_NEW, COL_DELTA):
                    self.table.item(row, col).setBackground(color)
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)

        invoice_total = invoice["total_amount"]
        mismatch = invoice_total and abs(line_total_sum - invoice_total) > 0.5
        text = f"Tổng các dòng đã nhập: {line_total_sum:,.0f} ₽".replace(",", ".")
        if invoice_total:
            text += f" — Tổng in trên hóa đơn: {invoice_total:,} ₽".replace(",", ".")
        if mismatch:
            text += "  ⚠ LỆCH SỐ — kiểm tra lại các dòng trước khi áp dụng."
        self.total_label.setText(text)
        self.paid_btn.setText("Đánh dấu CHƯA thanh toán" if invoice["paid"] else "Đánh dấu ĐÃ thanh toán cho NCC")

    def add_row(self):
        add_line(self.conn, self.invoice_id, raw_name="", raw_qty=1, raw_unit="шт", raw_unit_price=0)
        self.refresh()

    def add_known_lines(self):
        candidates = known_lines(self.conn)
        if not candidates:
            QMessageBox.information(
                self,
                "Chưa có mặt hàng quen thuộc",
                "Chưa có hóa đơn nào từng khớp mã hàng trước đây -- hãy gõ tay + \"Gợi ý mã hàng\" cho hóa đơn đầu tiên. "
                "Hóa đơn này sẽ trở thành mẫu cho các lần sau.",
            )
            return
        existing_codes = {
            line["matched_code"] for line in get_invoice(self.conn, self.invoice_id)["lines"] if line["matched_code"]
        }
        pickable = [c for c in candidates if c["matched_code"] not in existing_codes]
        if not pickable:
            QMessageBox.information(self, "Không có gì để thêm", "Mọi mặt hàng quen thuộc đều đã có trong bảng rồi.")
            return

        picker = _KnownLinesPickerDialog(self, pickable)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        selected = picker.selected_lines()
        if not selected:
            return
        for s in selected:
            add_line(
                self.conn,
                self.invoice_id,
                raw_name=s["raw_name"],
                raw_qty=s["raw_qty"],
                raw_unit=s["raw_unit"],
                raw_unit_price=None,  # always re-typed from THIS invoice's photo, never carried over
                matched_code=s["matched_code"],
                unit_conversion=s["unit_conversion"],
            )
        self.refresh()
        QMessageBox.information(
            self,
            "Đã thêm mặt hàng",
            f"Đã thêm {len(selected)} mặt hàng đã tích.\n\n"
            "Luôn tự gõ \"Đơn giá\" theo đúng hóa đơn đang xem (cột này cố tình để trống) -- "
            "giá không bao giờ được mang từ hóa đơn cũ sang.",
        )

    def remove_row(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._line_ids):
            return
        remove_line(self.conn, self._line_ids[row])
        self.refresh()

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        if row >= len(self._line_ids):
            return
        line_id = self._line_ids[row]
        try:
            raw_name = self.table.item(row, COL_NAME).text().strip()
            raw_qty_text = self.table.item(row, COL_QTY).text().strip().replace(",", ".")
            raw_qty = float(raw_qty_text) if raw_qty_text else None
            raw_unit = self.table.item(row, COL_UNIT).text().strip() or None
            raw_price_text = self.table.item(row, COL_PRICE).text().strip().replace(",", ".")
            raw_unit_price = float(raw_price_text) if raw_price_text else None
            conv_text = self.table.item(row, COL_CONV).text().strip().replace(",", ".")
            unit_conversion = float(conv_text) if conv_text else 1.0
            matched_code = self.table.item(row, COL_CODE).text().strip().upper() or None
        except ValueError:
            QMessageBox.warning(self, "Giá trị không hợp lệ", "Số lượng, đơn giá và hệ số quy đổi phải là số.")
            self.refresh()
            return
        if matched_code and get_product(self.conn, matched_code) is None:
            QMessageBox.warning(self, "Mã hàng không tồn tại", f"Không tìm thấy mã hàng '{matched_code}' trong danh mục.")
            matched_code = None
        update_line(
            self.conn,
            line_id,
            raw_name=raw_name,
            raw_qty=raw_qty,
            raw_unit=raw_unit,
            raw_unit_price=raw_unit_price,
            matched_code=matched_code,
            unit_conversion=unit_conversion,
        )
        self.refresh()

    def suggest_for_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._line_ids):
            return
        raw_name = self.table.item(row, COL_NAME).text().strip()
        if not raw_name:
            QMessageBox.information(self, "Chưa có tên", "Gõ tên mặt hàng trên hóa đơn vào cột đầu trước.")
            return
        matches = suggest_matches(self.conn, raw_name)
        if not matches:
            QMessageBox.information(self, "Không gợi ý được", "Không tìm thấy mặt hàng nào gần giống trong danh mục.")
            return
        from shop.core.products import list_products

        picker = _MatchPickerDialog(self, matches, list_products(self.conn, active_only=True))
        if picker.exec() and picker.selected_code:
            line_id = self._line_ids[row]
            update_line(self.conn, line_id, matched_code=picker.selected_code, unit_conversion=picker.selected_conversion)
            self.refresh()

    def apply_changes(self):
        invoice = get_invoice(self.conn, self.invoice_id)

        # Re-applying an invoice that was already applied once is how a
        # stray click overwrites a NEWER cost that came from a later
        # delivery of the same product -- this invoice's own lines look
        # perfectly normal, so only a warning that names the risk (not a
        # silent skip, which would make "Áp dụng" quietly do nothing and
        # look broken) catches it.
        if invoice["applied_at"]:
            proceed = QMessageBox.question(
                self,
                "Hóa đơn này đã áp dụng trước đó",
                f"Hóa đơn này đã áp dụng giá vào danh mục lúc {invoice['applied_at']}.\n\n"
                "Nếu có hóa đơn MỚI HƠN đã đổi giá mặt hàng nào đó sau đó, áp dụng lại bây giờ sẽ "
                "GHI ĐÈ bằng giá CŨ của hóa đơn này. Chỉ tiếp tục nếu bạn chắc chắn muốn áp dụng lại.",
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        unmatched = [l for l in invoice["lines"] if not l["matched_code"]]
        if unmatched:
            proceed = QMessageBox.question(
                self,
                "Còn dòng chưa khớp mã hàng",
                f"{len(unmatched)} dòng chưa chọn mã hàng khớp, sẽ bị bỏ qua. Tiếp tục áp dụng các dòng còn lại?",
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        # A line can be matched but still have no price -- the common
        # case now that "Thêm mặt hàng quen thuộc" (lần 22) pre-fills
        # name+code but always leaves "Đơn giá" blank on purpose. Without
        # this check, apply_invoice() would just silently skip it and
        # look like nothing went wrong.
        no_price = [l for l in invoice["lines"] if l["matched_code"] and l.get("raw_unit_price") is None]
        if no_price:
            names = "\n".join(f"- {l['matched_code']}: {l['raw_name']}" for l in no_price)
            proceed = QMessageBox.question(
                self,
                "Còn dòng chưa có đơn giá",
                f"{len(no_price)} dòng đã khớp mã hàng nhưng CHƯA gõ \"Đơn giá\", sẽ bị bỏ qua:\n{names}\n\n"
                "Tiếp tục áp dụng các dòng còn lại?",
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        big_changes = [
            (l, line_cost_preview(self.conn, l))
            for l in invoice["lines"]
            if l["matched_code"]
        ]
        big_changes = [(l, p) for l, p in big_changes if p["delta_pct"] is not None and abs(p["delta_pct"]) >= 30]
        if big_changes:
            summary = "\n".join(
                f"- {l['matched_code']}: {p['old_cost']:.2f} → {p['new_cost']:.2f} ₽ ({p['delta_pct']:+.0f}%)"
                for l, p in big_changes
            )
            proceed = QMessageBox.question(
                self,
                "Giá thay đổi rất lớn",
                f"{len(big_changes)} mặt hàng đổi giá từ 30% trở lên — rất có thể do nhầm hệ số quy đổi "
                f"(vd. nhập cả thùng nhưng quên chia), hoặc đây thực sự là giá mới:\n\n{summary}\n\n"
                "Kiểm tra lại cột \"Quy đổi\" trước khi tiếp tục. Vẫn áp dụng?",
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        applied = apply_invoice(self.conn, self.invoice_id)
        if not applied:
            QMessageBox.information(self, "Không có gì để áp dụng", "Chưa có dòng nào vừa khớp mã hàng vừa có đơn giá.")
            return

        # A DRAFT customer invoice already holding one of these products has
        # a now-stale cost_price_snapshot (see shop.core.invoices) -- flag
        # it instead of letting the owner finalize with an outdated profit.
        changed_codes = {a["matched_code"] for a in applied}
        placeholders = ",".join("?" * len(changed_codes))
        stale = self.conn.execute(
            f"""
            SELECT DISTINCT i.id FROM invoice_lines l
            JOIN invoices i ON i.id = l.invoice_id
            WHERE i.status = 'draft' AND l.product_code IN ({placeholders})
            """,
            tuple(changed_codes),
        ).fetchall()

        lines_summary = "\n".join(
            f"- {a['matched_code']}: {a['old_cost']:.2f} → {a['new_cost']:.2f} ₽"
            + (f" ({a['delta_pct']:+.1f}%)" if a["delta_pct"] else "")
            for a in applied
        )
        msg = f"Đã cập nhật giá vốn cho {len(applied)} mặt hàng:\n{lines_summary}"
        if stale:
            msg += (
                f"\n\n⚠ {len(stale)} hóa đơn khách đang NHÁP có chứa mặt hàng vừa đổi giá — "
                "kiểm tra lại cột \"Giá vốn\" của dòng đó trước khi hoàn tất, nếu không lợi nhuận sẽ tính sai."
            )
        msg += '\n\nGiá công khai trên website KHÔNG tự đổi theo — bấm "Cập nhật website giá" ở tab Danh mục hàng nếu muốn.'
        QMessageBox.information(self, "Đã áp dụng", msg)
        self.refresh()

    def toggle_paid(self):
        invoice = get_invoice(self.conn, self.invoice_id)
        set_paid(self.conn, self.invoice_id, not invoice["paid"])
        self.refresh()
