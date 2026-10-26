import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
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

from shop.core.arrival_notify import NotifyError, send_arrival_notifications
from shop.core.customers import list_customers
from shop.core.online_orders import (
    SyncError,
    batch_delivered_by_code,
    batch_demand_by_code,
    batch_excluded_codes,
    batch_linked_invoices,
    batch_shortage_report,
    close_batch,
    convert_to_invoice,
    link_invoice_to_batch,
    linked_customer_id,
    list_batch_order_lines_for_code,
    list_batches,
    list_online_orders,
    mark_cancelled,
    order_batch_label,
    pending_demand_by_code,
    set_code_excluded,
    set_order_line_excluded,
    set_order_line_qty,
    sync_from_bot,
    unlink_invoice_from_batch,
)
from shop.core.supplier_invoices import list_invoices
from shop.paths import bot_sync_settings, set_bot_sync_settings
from shop.ui.dialogs import BotSyncSettingsDialog, CustomerPickerDialog
from shop.ui.invoice_editor import InvoiceEditorDialog

HEADERS = ["#", "Đợt", "Khách hàng", "SĐT", "Mặt hàng", "Tổng ước tính (RUB)", "Ngày đặt", "Trạng thái"]
STATUS_LABELS = {"cho_xu_ly": "Chờ xử lý", "da_tao_hoa_don": "Đã tạo hóa đơn", "da_huy": "Đã hủy"}


class OnlineOrdersPage(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._orders: list[dict] = []

        sync_btn = QPushButton("🔄 Đồng bộ ngay")
        sync_btn.clicked.connect(self.sync_now)
        settings_btn = QPushButton("Cài đặt đồng bộ…")
        settings_btn.clicked.connect(self.open_settings)
        demand_btn = QPushButton("Cần nhập hàng gì?")
        demand_btn.clicked.connect(self.show_demand)
        convert_btn = QPushButton("Tạo hóa đơn từ đơn này")
        convert_btn.clicked.connect(self.convert_selected)
        cancel_btn = QPushButton("Hủy đơn")
        cancel_btn.clicked.connect(self.cancel_selected)

        top = QHBoxLayout()
        top.addWidget(sync_btn)
        top.addWidget(settings_btn)
        top.addWidget(demand_btn)
        top.addStretch()
        top.addWidget(convert_btn)
        top.addWidget(cancel_btn)

        # Second row, separate from the per-order actions above: "chốt
        # đợt" (request #2, lần 19) operates on every pending order at
        # once, roughly every 2 tuần, not on whatever row is selected.
        close_batch_btn = QPushButton("📦 Chốt đợt hàng mới")
        close_batch_btn.clicked.connect(self.close_batch_now)
        review_batch_btn = QPushButton("Duyệt đợt hàng gần nhất…")
        review_batch_btn.clicked.connect(self.review_latest_batch)

        batch_row = QHBoxLayout()
        batch_row.addWidget(close_batch_btn)
        batch_row.addWidget(review_batch_btn)
        batch_row.addStretch()

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(batch_row)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        # Chờ xử lý trước (việc cần làm), rồi mới tới đã xử lý/đã hủy, để
        # người dùng không phải lướt qua lịch sử cũ mới thấy việc cần làm.
        pending = list_online_orders(self.conn, status="cho_xu_ly")
        done = [o for o in list_online_orders(self.conn) if o["status"] != "cho_xu_ly"]
        self._orders = pending + done

        self.table.setRowCount(len(self._orders))
        for row, o in enumerate(self._orders):
            items_summary = ", ".join(
                f"{line['name_at_order']} x{line['qty']:g}" + (" (đã loại)" if line["excluded"] else "")
                for line in o["lines"]
            )
            values = [
                str(o["id"]),
                order_batch_label(o["batch_id"]),
                o["customer_label"],
                o["customer_phone"] or "",
                items_summary,
                f"{o['total_estimated']:,}".replace(",", "."),
                o["placed_at"],
                STATUS_LABELS.get(o["status"], o["status"]),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def _selected_order(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._orders):
            return None
        return self._orders[row]

    def sync_now(self):
        worker_url, sync_secret = bot_sync_settings()
        if not worker_url or not sync_secret:
            QMessageBox.information(
                self,
                "Chưa cài đặt đồng bộ",
                'Bấm "Cài đặt đồng bộ…" trước, dán Worker URL và Mã đồng bộ (xem bot/README.md).',
            )
            return
        # sync_from_bot() is a blocking socket call on the UI thread --
        # not fixed here (would need a worker thread), but at least
        # give a visible sign that the app is doing something instead
        # of looking frozen on a slow/throttled connection.
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            inserted = sync_from_bot(self.conn, worker_url, sync_secret)
        except SyncError as e:
            QMessageBox.warning(self, "Không đồng bộ được", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh()
        if inserted > 0:
            QMessageBox.information(self, "Đã đồng bộ", f"Có {inserted} đơn hàng mới.")
        else:
            QMessageBox.information(self, "Đã đồng bộ", "Không có đơn hàng mới.")

    def open_settings(self):
        worker_url, sync_secret = bot_sync_settings()
        dialog = BotSyncSettingsDialog(self, worker_url, sync_secret)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            set_bot_sync_settings(*dialog.values())

    def show_demand(self):
        # pending_demand_by_code() is scoped to orders NOT YET in a batch
        # (lần 19) -- this is a PREVIEW of what's piling up for the next
        # "Chốt đợt hàng mới", not the list to actually order from the
        # supplier. For a batch already chốt, use "Duyệt đợt hàng…"
        # instead (that one is also pruned of items already loại bỏ).
        demand = pending_demand_by_code(self.conn)
        dialog = QDialog(self)
        dialog.setWindowTitle("Cần nhập hàng gì (đơn CHƯA thuộc đợt nào)")
        dialog.resize(504, 576)  # 420x480 * 1.2 (request #3, lần 19)

        layout = QVBoxLayout(dialog)
        hint = QLabel(
            "Đây là đơn CHƯA chốt vào đợt nào -- để xem danh sách THẬT SỰ cần đặt nhà cung cấp "
            'cho đợt đã chốt, dùng "Duyệt đợt hàng gần nhất…" thay vì bảng này.'
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        if not demand:
            layout.addWidget(QLabel("Không có đơn nào đang chờ xử lý, chưa thuộc đợt nào."))
        else:
            table = QTableWidget(len(demand), 3)
            table.setHorizontalHeaderLabels(["Mã hàng", "Tên", "Tổng số lượng khách chờ"])
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            for row, d in enumerate(demand):
                table.setItem(row, 0, QTableWidgetItem(d["code"]))
                table.setItem(row, 1, QTableWidgetItem(d["name"]))
                table.setItem(row, 2, QTableWidgetItem(f"{d['total_qty']:g}"))
            table.resizeColumnsToContents()
            layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def convert_selected(self):
        order = self._selected_order()
        if order is None:
            return
        if order["status"] != "cho_xu_ly":
            QMessageBox.information(self, "Đơn đã xử lý", "Đơn này đã tạo hóa đơn hoặc đã hủy rồi.")
            return

        customers = list_customers(self.conn, active_only=True)
        preselected = linked_customer_id(self.conn, order["telegram_chat_id"])
        if preselected is not None and any(c["id"] == preselected for c in customers):
            # Đã từng chốt khách này với đúng chat Telegram này trước đây --
            # hỏi lại 1 câu xác nhận nhanh thay vì bắt tìm lại trong danh sách.
            name = next(c["name"] for c in customers if c["id"] == preselected)
            confirm = QMessageBox.question(
                self,
                "Dùng khách hàng cũ?",
                f'Đơn trước của chat Telegram này đã gắn với khách "{name}". Dùng lại khách này?',
            )
            if confirm == QMessageBox.StandardButton.Yes:
                customer_id = preselected
            else:
                customer_id = self._pick_customer(customers, order)
                if customer_id is None:
                    return
        else:
            customer_id = self._pick_customer(customers, order)
            if customer_id is None:
                return

        try:
            invoice_id, dropped, excluded = convert_to_invoice(self.conn, order["id"], customer_id)
        except ValueError as e:
            QMessageBox.information(self, "Không còn gì để lên hóa đơn", str(e))
            return
        self.refresh()
        if excluded:
            QMessageBox.information(
                self,
                "Có mặt hàng đã bị loại ở đợt hàng",
                f"Các mã sau đã bị loại (hết hàng, duyệt ở đợt hàng) nên không có trong hóa đơn: {', '.join(excluded)}",
            )
        if dropped:
            QMessageBox.warning(
                self,
                "Có mặt hàng không nhận diện được",
                f"Các mã sau không còn trong danh mục, chưa được thêm vào hóa đơn: {', '.join(dropped)}",
            )
        dialog = InvoiceEditorDialog(self, self.conn, invoice_id)
        dialog.exec()
        self.refresh()

    def _pick_customer(self, customers: list[dict], order: dict) -> int | None:
        picker = CustomerPickerDialog(
            self, self.conn, customers, suggested_name=order["customer_label"], suggested_phone=order["customer_phone"] or ""
        )
        if picker.exec() != QDialog.DialogCode.Accepted or picker.selected_customer_id is None:
            return None
        return picker.selected_customer_id

    def cancel_selected(self):
        order = self._selected_order()
        if order is None:
            return
        if order["status"] != "cho_xu_ly":
            return
        confirm = QMessageBox.question(self, "Hủy đơn?", f'Hủy đơn của "{order["customer_label"]}"?')
        if confirm == QMessageBox.StandardButton.Yes:
            mark_cancelled(self.conn, order["id"])
            self.refresh()

    def close_batch_now(self):
        # Sync first (best-effort) so an order the customer already
        # placed but the app hasn't pulled in yet still gets a chance to
        # land in THIS batch instead of waiting an extra ~2 weeks for no
        # reason -- see close_batch's docstring for why this isn't airtight.
        worker_url, sync_secret = bot_sync_settings()
        if worker_url and sync_secret:
            try:
                sync_from_bot(self.conn, worker_url, sync_secret)
            except SyncError:
                pass  # không chặn việc chốt đợt chỉ vì lỗi mạng tạm thời

        pending_count = len([o for o in list_online_orders(self.conn, status="cho_xu_ly") if o["batch_id"] is None])
        if pending_count == 0:
            QMessageBox.information(self, "Không có đơn để chốt", "Không có đơn 'Chờ xử lý' nào chưa thuộc đợt nào.")
            return
        confirm = QMessageBox.question(
            self,
            "Chốt đợt hàng mới?",
            f"Sẽ gộp {pending_count} đơn 'Chờ xử lý' chưa thuộc đợt nào vào 1 đợt hàng mới. "
            "Đơn khách đặt sau khi chốt sẽ chờ đợt kế tiếp. Tiếp tục?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        batch_id = close_batch(self.conn)
        self.refresh()
        QMessageBox.information(
            self,
            "Đã chốt đợt hàng",
            f'Đợt #{batch_id} đã chốt {pending_count} đơn. Bấm "Duyệt đợt hàng gần nhất…" để xem cần nhập gì '
            "và loại mặt hàng nhà cung cấp không có.",
        )

    def review_latest_batch(self):
        batches = list_batches(self.conn)
        if not batches:
            QMessageBox.information(self, "Chưa có đợt hàng", 'Bấm "📦 Chốt đợt hàng mới" trước để tạo đợt hàng đầu tiên.')
            return
        dialog = BatchReviewDialog(self, self.conn, batches[0]["id"])
        dialog.exec()
        self.refresh()


class BatchReviewDialog(QDialog):
    """Lets the owner strike an item the supplier doesn't have from
    every pending order in a batch at once (request #1), instead of
    hunting through orders one by one -- and undo it on a misclick."""

    def __init__(self, parent, conn: sqlite3.Connection, batch_id: int):
        super().__init__(parent)
        self.conn = conn
        self.batch_id = batch_id
        self.setWindowTitle(f"Duyệt đợt hàng #{batch_id}")
        self.resize(672, 672)  # 560x560 * 1.2 (request #3, lần 19)

        hint = QLabel(
            "Loại 1 mặt hàng sẽ bỏ nó khỏi MỌI đơn trong đợt này (khách chỉ nhận + trả tiền phần còn lại); "
            "chọn 1 mặt hàng ở bảng dưới và bấm 'Khôi phục' nếu loại nhầm."
        )
        hint.setWordWrap(True)

        self.demand_table = QTableWidget(0, 4)
        self.demand_table.setHorizontalHeaderLabels(["Mã hàng", "Tên", "Tổng SL chờ", "Số đơn"])
        self.demand_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.demand_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        exclude_btn = QPushButton("Loại mặt hàng này (hết hàng)")
        exclude_btn.clicked.connect(self._exclude_selected)

        self.excluded_table = QTableWidget(0, 3)
        self.excluded_table.setHorizontalHeaderLabels(["Mã hàng", "Tên", "Số đơn bị ảnh hưởng"])
        self.excluded_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.excluded_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        restore_btn = QPushButton("Khôi phục mặt hàng đã chọn")
        restore_btn.clicked.connect(self._restore_selected)

        # "Hàng đã về" (request 25/10/2026): nối đợt này với (các) hóa
        # đơn NCC thật sự giao hàng, rồi gửi DM riêng cho từng khách --
        # xem shop.core.arrival_notify.
        self.invoices_list = QListWidget()
        link_invoice_btn = QPushButton("Nối với hóa đơn NCC…")
        link_invoice_btn.clicked.connect(self._link_invoice)
        unlink_invoice_btn = QPushButton("Gỡ hóa đơn đã chọn")
        unlink_invoice_btn.clicked.connect(self._unlink_invoice)
        notify_btn = QPushButton("📨 Kiểm tra & gửi thông báo khách hàng…")
        notify_btn.clicked.connect(self._check_and_notify)

        invoice_buttons = QHBoxLayout()
        invoice_buttons.addWidget(link_invoice_btn)
        invoice_buttons.addWidget(unlink_invoice_btn)

        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(QLabel("Cần nhập hàng (chưa loại):"))
        layout.addWidget(self.demand_table)
        layout.addWidget(exclude_btn)
        layout.addWidget(QLabel("Đã loại khỏi đợt này:"))
        layout.addWidget(self.excluded_table)
        layout.addWidget(restore_btn)
        layout.addWidget(QLabel("Hóa đơn nhà cung cấp đã nối với đợt này (hàng thật sự đã về):"))
        layout.addWidget(self.invoices_list)
        layout.addLayout(invoice_buttons)
        layout.addWidget(notify_btn)
        layout.addWidget(close_btn)

        self.refresh()

    def refresh(self):
        self._demand = batch_demand_by_code(self.conn, self.batch_id)
        self.demand_table.setRowCount(len(self._demand))
        for row, d in enumerate(self._demand):
            for col, value in enumerate([d["code"], d["name"], f"{d['total_qty']:g}", str(d["order_count"])]):
                self.demand_table.setItem(row, col, QTableWidgetItem(value))
        self.demand_table.resizeColumnsToContents()

        self._excluded = batch_excluded_codes(self.conn, self.batch_id)
        self.excluded_table.setRowCount(len(self._excluded))
        for row, d in enumerate(self._excluded):
            for col, value in enumerate([d["code"], d["name"], str(d["order_count"])]):
                self.excluded_table.setItem(row, col, QTableWidgetItem(value))
        self.excluded_table.resizeColumnsToContents()

        self._linked_invoices = batch_linked_invoices(self.conn, self.batch_id)
        self.invoices_list.clear()
        for inv in self._linked_invoices:
            label = inv["invoice_number"] or f"(chưa đặt số) #{inv['id']}"
            applied = "đã áp dụng giá" if inv["applied_at"] else "CHƯA áp dụng giá"
            item = QListWidgetItem(f"{label} -- {inv['invoice_date'] or '?'} -- {applied}")
            item.setData(Qt.ItemDataRole.UserRole, inv["id"])
            self.invoices_list.addItem(item)

    def _exclude_selected(self):
        row = self.demand_table.currentRow()
        if row < 0 or row >= len(self._demand):
            return
        code = self._demand[row]["code"]
        confirm = QMessageBox.question(
            self, "Loại mặt hàng?", f'Loại "{code}" khỏi mọi đơn trong đợt này? Khách sẽ không bị tính tiền món này.'
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        affected = set_code_excluded(self.conn, self.batch_id, code, excluded=True)
        self.refresh()
        QMessageBox.information(self, "Đã loại", f"Đã loại khỏi {len(affected)} đơn hàng.")

    def _restore_selected(self):
        row = self.excluded_table.currentRow()
        if row < 0 or row >= len(self._excluded):
            return
        code = self._excluded[row]["code"]
        affected = set_code_excluded(self.conn, self.batch_id, code, excluded=False)
        self.refresh()
        QMessageBox.information(self, "Đã khôi phục", f"Đã khôi phục ở {len(affected)} đơn hàng.")

    def _link_invoice(self):
        already_linked = {inv["id"] for inv in self._linked_invoices}
        candidates = [inv for inv in list_invoices(self.conn) if inv["order_batch_id"] is None]
        if not candidates:
            QMessageBox.information(
                self, "Không có hóa đơn để nối",
                "Không có hóa đơn nhà cung cấp nào chưa nối với đợt khác. "
                "Nhập hóa đơn ở tab \"Hóa đơn nhà cung cấp\" trước (chụp ảnh hoặc dùng /hangve).",
            )
            return
        labels = [
            f"{inv['invoice_number'] or '(chưa đặt số)'} -- {inv['invoice_date'] or '?'} -- #{inv['id']}"
            for inv in candidates
        ]
        label, ok = QInputDialog.getItem(self, "Nối với hóa đơn NCC", "Chọn hóa đơn:", labels, editable=False)
        if not ok:
            return
        invoice = candidates[labels.index(label)]
        if not invoice["applied_at"]:
            confirm = QMessageBox.question(
                self, "Hóa đơn chưa áp dụng giá",
                "Hóa đơn này CHƯA bấm \"Áp dụng giá mới vào danh mục\" -- vẫn nối được, nhưng nên hoàn tất "
                "khớp mã hàng trước khi kiểm tra thiếu/thừa, nếu không số liệu có thể sai. Vẫn nối?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        link_invoice_to_batch(self.conn, invoice["id"], self.batch_id)
        self.refresh()

    def _unlink_invoice(self):
        item = self.invoices_list.currentItem()
        if item is None:
            return
        invoice_id = item.data(Qt.ItemDataRole.UserRole)
        unlink_invoice_from_batch(self.conn, invoice_id)
        self.refresh()

    def _check_and_notify(self):
        if not self._linked_invoices:
            QMessageBox.information(
                self, "Chưa nối hóa đơn NCC",
                "Nối ít nhất 1 hóa đơn nhà cung cấp với đợt này trước (hàng thật sự đã về), "
                "rồi mới gửi thông báo cho khách.",
            )
            return

        _delivered, incomplete = batch_delivered_by_code(self.conn, self.batch_id)
        if incomplete > 0:
            QMessageBox.warning(
                self, "Hóa đơn chưa khớp đủ",
                f"Có {incomplete} dòng trong (các) hóa đơn NCC đã nối chưa khớp mã hàng hoặc chưa ghi số lượng -- "
                "số liệu thiếu/thừa sẽ không chính xác. Mở hóa đơn đó (tab \"Hóa đơn nhà cung cấp\"), "
                "hoàn tất khớp/gõ số lượng rồi quay lại đây.",
            )
            return

        shortage = batch_shortage_report(self.conn, self.batch_id)
        if shortage:
            dialog = _ShortageReconcileDialog(self, self.conn, self.batch_id, shortage)
            dialog.exec()

        pending = len(
            [o for o in list_online_orders(self.conn, status="cho_xu_ly")
             if o["batch_id"] == self.batch_id and o["arrival_notified_at"] is None]
        )
        if pending == 0:
            QMessageBox.information(self, "Không có gì để gửi", "Mọi khách trong đợt này đã được thông báo rồi.")
            return
        confirm = QMessageBox.question(
            self, "Gửi thông báo?",
            f"Sẽ gửi {pending} tin nhắn Telegram riêng cho {pending} khách, báo hàng đã về. "
            "KHÔNG thể thu hồi sau khi gửi. Gửi ngay?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        worker_url, sync_secret = bot_sync_settings()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = send_arrival_notifications(self.conn, self.batch_id, worker_url, sync_secret)
        except NotifyError as e:
            QMessageBox.warning(self, "Không gửi được", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()

        msg = f"Đã gửi {len(result['sent'])} tin."
        if result["failed"]:
            names = "\n".join(f"- {f['customer_label']}: {f['error']}" for f in result["failed"])
            msg += f"\n\n{len(result['failed'])} khách gửi KHÔNG thành công, cần tự liên hệ:\n{names}"
        QMessageBox.information(self, "Đã gửi thông báo", msg)
        self.refresh()


class _ShortageReconcileDialog(QDialog):
    """Opened when batch_shortage_report() found a mismatch between what
    was ordered and what the linked supplier invoice(s) show as
    delivered -- request 25/10/2026 ("tôi sẽ cần tinh chỉnh lại các đơn
    của khách... thiếu hay thừa"). NOT automatic reallocation: the owner
    picks which customer's line to adjust, one at a time."""

    def __init__(self, parent, conn: sqlite3.Connection, batch_id: int, shortage: list[dict]):
        super().__init__(parent)
        self.conn = conn
        self.batch_id = batch_id
        self.setWindowTitle("Đối chiếu thiếu/thừa với hóa đơn NCC")
        self.resize(720, 600)

        hint = QLabel(
            "Chênh lệch dương = thiếu (về ít hơn tổng đã đặt), âm = thừa. "
            "Chọn 1 mặt hàng để xem từng đơn khách, rồi sửa số lượng hoặc loại khỏi đơn đó nếu cần. "
            "Mặt hàng khớp đủ không hiện ở đây -- không cần chỉnh gì."
        )
        hint.setWordWrap(True)

        self.shortage_table = QTableWidget(0, 5)
        self.shortage_table.setHorizontalHeaderLabels(["Mã hàng", "Tên", "Đã đặt", "Đã về", "Chênh lệch"])
        self.shortage_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.shortage_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.shortage_table.currentCellChanged.connect(lambda *_: self._refresh_lines())

        self.lines_table = QTableWidget(0, 4)
        self.lines_table.setHorizontalHeaderLabels(["Khách hàng", "SL hiện tại", "SL khách đặt ban đầu", "Trạng thái"])
        self.lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        edit_qty_btn = QPushButton("Sửa số lượng dòng đã chọn…")
        edit_qty_btn.clicked.connect(self._edit_qty)
        toggle_exclude_btn = QPushButton("Loại / Khôi phục dòng đã chọn")
        toggle_exclude_btn.clicked.connect(self._toggle_exclude)
        done_btn = QPushButton("Xong")
        done_btn.clicked.connect(self.accept)

        line_buttons = QHBoxLayout()
        line_buttons.addWidget(edit_qty_btn)
        line_buttons.addWidget(toggle_exclude_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.shortage_table)
        layout.addWidget(QLabel("Từng đơn khách cho mặt hàng đã chọn ở trên:"))
        layout.addWidget(self.lines_table)
        layout.addLayout(line_buttons)
        layout.addWidget(done_btn)

        self._set_shortage(shortage)

    def _set_shortage(self, shortage: list[dict]):
        self._shortage = shortage
        self.shortage_table.setRowCount(len(shortage))
        for row, s in enumerate(shortage):
            values = [s["code"], s["name"], f"{s['ordered']:g}", f"{s['delivered']:g}", f"{s['diff']:+g}"]
            for col, value in enumerate(values):
                self.shortage_table.setItem(row, col, QTableWidgetItem(value))
        self.shortage_table.resizeColumnsToContents()
        self._refresh_lines()

    def _selected_code(self) -> str | None:
        row = self.shortage_table.currentRow()
        if row < 0 or row >= len(self._shortage):
            return None
        return self._shortage[row]["code"]

    def _refresh_lines(self):
        code = self._selected_code()
        self._lines = list_batch_order_lines_for_code(self.conn, self.batch_id, code) if code else []
        self.lines_table.setRowCount(len(self._lines))
        for row, l in enumerate(self._lines):
            status = "Đã loại" if l["excluded"] else "Bình thường"
            values = [
                l["customer_label"],
                f"{l['qty']:g}",
                f"{l['original_qty']:g}" if l["original_qty"] is not None else "",
                status,
            ]
            for col, value in enumerate(values):
                self.lines_table.setItem(row, col, QTableWidgetItem(value))
        self.lines_table.resizeColumnsToContents()

    def _edit_qty(self):
        row = self.lines_table.currentRow()
        if row < 0 or row >= len(self._lines):
            return
        line = self._lines[row]
        new_qty, ok = QInputDialog.getDouble(
            self, "Sửa số lượng", f"Số lượng mới cho {line['customer_label']}:", value=line["qty"], min=0.01, decimals=2
        )
        if not ok:
            return
        set_order_line_qty(self.conn, line["line_id"], new_qty)
        self._refresh_lines()

    def _toggle_exclude(self):
        row = self.lines_table.currentRow()
        if row < 0 or row >= len(self._lines):
            return
        line = self._lines[row]
        set_order_line_excluded(self.conn, line["line_id"], not line["excluded"])
        self._refresh_lines()
