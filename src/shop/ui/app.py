import os
import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from shop.db.backup import backup_now
from shop.db.migrate import connect
from shop.ui.branding import icon_path
from shop.ui.main_window import MainWindow


def _app_icon() -> QIcon:
    path = icon_path()
    return QIcon(str(path)) if path else QIcon()


# Lần 25: "điểm nhấn" theme (AskUserQuestion -- giữ giao diện Windows gốc,
# chỉ đổi màu nút chính sang cyan thương hiệu + dải navy ở Tổng quan, xem
# dashboard_page._HeaderBand). Chỉ nhắm QPushButton -- không đụng QLabel/
# QLineEdit/bảng... nên mọi trang khác giữ nguyên 100% như trước.
_ACCENT_STYLESHEET = """
QPushButton {
    background-color: #0e7490;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #0891a8; }
QPushButton:pressed { background-color: #0c6a82; }
QPushButton:disabled { background-color: #9ca3af; color: #e5e7eb; }
"""


def _apply_scaled_font(app: QApplication, factor: float = 1.2) -> None:
    """Request #3, lần 19: "mọi chữ và nút tăng kích thước 20%". One
    app-wide font bump instead of touching every page's stylesheet --
    QPushButton/QLabel/table headers etc. all inherit the default font
    unless a widget sets its own pixel size explicitly (dashboard_page.py
    does, for its big numbers -- those are bumped by hand there since a
    literal "font-size: 32px" in a stylesheet doesn't scale with this).
    Guards pointSizeF() == -1, which means the platform font is defined
    in pixels, not points -- scaling the wrong one would be a no-op."""
    font = app.font()
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() * factor)
    elif font.pixelSize() > 0:
        font.setPixelSize(round(font.pixelSize() * factor))
    app.setFont(font)


def main():
    if "--self-test" in sys.argv:
        sys.exit(self_test())

    app = QApplication(sys.argv)
    _apply_scaled_font(app)
    app.setWindowIcon(_app_icon())
    app.setStyleSheet(_ACCENT_STYLESHEET)
    try:
        backup_now()
    except OSError:
        pass  # never block startup over a failed backup
    conn = connect()
    window = MainWindow(conn)
    window.show()
    sys.exit(app.exec())


def self_test() -> int:
    """Smoke-test a build (dev or frozen): migrations load, the bundled
    site template is readable, and every tab renders without crashing.
    Used by the build scripts, and by whoever is verifying a build by
    hand -- it has no normal stdout once frozen (windowed exe), so it
    writes PNGs + a result file into the directory named by
    SHOP_SELFTEST_OUT instead of printing.

    Requires SHOP_DATA_DIR to be set (refuses to run otherwise), so a
    self-test can never accidentally open the real ledger.
    """
    out_dir = Path(os.environ.get("SHOP_SELFTEST_OUT", "selftest-output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "result.txt"

    if not os.environ.get("SHOP_DATA_DIR"):
        result_path.write_text("FAIL: SHOP_DATA_DIR must be set before running --self-test\n", encoding="utf-8")
        return 2

    try:
        import openpyxl
        from importlib import resources

        from shop.core.customers import add_customer
        from shop.core.invoices import add_line, create_invoice, finalize_invoice, invoice_profit
        from shop.core.payments import add_payment
        from shop.core.summary import customer_debt
        from shop.excel.catalog_export import export_catalog
        from shop.excel.invoice_export import export_invoice
        from shop.excel.summary_export import export_summary
        from shop.tools.import_xlsx import import_catalog

        app = QApplication(sys.argv)
        _apply_scaled_font(app)
        app.setWindowIcon(_app_icon())
        app.setStyleSheet(_ACCENT_STYLESHEET)
        if app.windowIcon().isNull():
            raise RuntimeError("app icon failed to load (packaging/bundling problem)")

        conn = connect()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            raise RuntimeError(f"unexpected schema version: {version}")

        index_html = (resources.files("shop.site_template") / "index.html").read_text(encoding="utf-8")
        if "<html" not in index_html.lower():
            raise RuntimeError("site_template/index.html did not read back as expected")

        # Exercise openpyxl (import) under the frozen build, not just at
        # dev time, with a tiny synthetic BANG GIA HUP-shaped workbook.
        tmp_xlsx = out_dir / "_selftest_catalog.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "BANG GIA HUP"
        ws.append(["ID", "TEN", "DVT", "GOC", "HUP", "SLL", "GIA_SLL", "TRANG_THAI"])
        ws.append(["GAO001", "Gao Jasmin Aroy-D Thai Lan 4,5 Kg", "KG", 277.7777777777778, 305.55, 4.5, 1375, True])
        ws.append(["BADAM1", "Banh Da Me 350gr", "goi", 350, 385, 0, 0, True])
        wb.save(tmp_xlsx)
        written, skipped = import_catalog(conn, tmp_xlsx)  # insert-only: fine whether the DB is empty or has these codes already
        if written + skipped != 2:
            raise RuntimeError(f"unexpected import_catalog result: written={written} skipped={skipped}")

        # Seed a realistic invoice (fractional qty line) end to end and
        # check the numbers, not just that nothing crashed.
        customer_id = add_customer(conn, "Khach tu self-test", default_markup_pct=12)
        invoice_id = create_invoice(conn, customer_id)
        add_line(conn, invoice_id, "GAO001", qty=2.5, markup_pct=12)  # 277.78 * 1.12 = 311 (round-half-up) * 2.5 = 778
        add_line(conn, invoice_id, "BADAM1", qty=3, markup_pct=12)  # 350 * 1.12 = 392 * 3 = 1176
        finalize_invoice(conn, invoice_id)
        add_payment(conn, customer_id, 500)

        total = 778 + 1176
        expected_debt = total - 500
        actual_debt = customer_debt(conn, customer_id)
        if actual_debt != expected_debt:
            raise RuntimeError(f"debt mismatch: expected {expected_debt}, got {actual_debt}")

        cost_total = round(277.7777777777778 * 2.5) + 350 * 3  # 694 + 1050 = 1744
        expected_profit = total - cost_total
        actual_profit = invoice_profit(conn, invoice_id)
        if actual_profit != expected_profit:
            raise RuntimeError(f"profit mismatch: expected {expected_profit}, got {actual_profit}")

        export_catalog(conn, out_dir / "selftest-catalog.xlsx")
        export_invoice(conn, invoice_id, out_dir / "selftest-invoice.xlsx")
        export_summary(conn, out_dir / "selftest-summary.xlsx")

        # The OCR assist is optional (Tesseract itself is a manual install,
        # and the Mac build won't have it at all -- see shop.ocr.engine),
        # but the bundled rus/eng *language data* must always be present:
        # this checks packaging, not the OCR engine, so it never needs
        # tesseract.exe to be installed on the machine running self-test.
        for lang_file in ("rus.traineddata", "eng.traineddata"):
            data = (resources.files("shop.ocr") / lang_file).read_bytes()
            if len(data) < 1024:
                raise RuntimeError(f"shop.ocr/{lang_file} did not bundle correctly ({len(data)} bytes)")

        # Supplier-invoice import, end to end on synthetic data: create ->
        # add a line with a case-of-30 unit conversion -> apply -> check
        # the catalog cost actually changed to the per-piece price, not
        # the raw case price.
        from shop.core.supplier_invoices import add_line as add_supplier_line
        from shop.core.supplier_invoices import apply_invoice as apply_supplier_invoice
        from shop.core.supplier_invoices import create_invoice as create_supplier_invoice
        from shop.core.products import get_product as get_test_product

        si_id = create_supplier_invoice(conn, invoice_number="SELFTEST-1")
        add_supplier_line(
            conn, si_id, raw_name="Banh Da Me 350gr case of 10", raw_qty=1, raw_unit="кор (10 шт)",
            raw_unit_price=4000, matched_code="BADAM1", unit_conversion=10,
        )
        applied = apply_supplier_invoice(conn, si_id)
        if len(applied) != 1 or get_test_product(conn, "BADAM1")["cost_price"] != 400:
            raise RuntimeError(f"supplier invoice apply did not normalize cost per unit: {applied}")

        # shop.ui.local_image ("Chọn ảnh từ máy..." in ProductDialog)
        # writes a JPEG via Qt, not Pillow -- check that write path
        # actually works in THIS build (packaged Qt's imageformats
        # plugin could in principle be missing) without going through
        # apply_local_image itself, since that hardcodes site_repo_dir()
        # and would pollute the real website's images/ folder with a
        # throwaway test file.
        from PySide6.QtGui import QImage, QColor

        probe_img = QImage(500, 400, QImage.Format.Format_RGB32)
        probe_img.fill(QColor("red"))
        probe_path = out_dir / "selftest-local-image.jpg"
        if not probe_img.save(str(probe_path), "JPG", quality=88):
            raise RuntimeError("Qt could not write a JPEG in this build (imageformats plugin missing?)")
        reloaded = QImage(str(probe_path))
        if reloaded.isNull():
            raise RuntimeError("Qt wrote a JPEG that it then couldn't read back")

        # Frozen builds (PyInstaller) can silently miss the CA cert
        # bundle Python's ssl module needs, which breaks EVERY
        # https:// call from the packaged exe while the exact same
        # code works fine under `uv run` -- a packaging failure mode,
        # not a logic one (shop.core.online_orders's own tests already
        # cover the logic with a mocked urlopen). This hits the REAL
        # deployed Worker; no real SYNC_SECRET needed since ANY value
        # gets a 403 (fail-closed) -- that 403 is exactly what proves
        # the HTTPS/TLS round trip itself worked.
        import ssl
        import urllib.error
        import urllib.request

        https_check = "skipped (no network)"
        try:
            req = urllib.request.Request(
                "https://705bot-telegram.705bot-telegram-bot.workers.dev/sync/orders",
                # Must match shop.core.online_orders.sync_from_bot's own
                # headers: Cloudflare's edge bot protection blocks
                # Python's default "Python-urllib/..." User-Agent with
                # its OWN 403 (body "error code: 1010") before the
                # request ever reaches the Worker -- confirmed live.
                # Without this, "403 ok" below could be the edge
                # blocking us, not the Worker's own fail-closed check.
                headers={"X-Sync-Secret": "selftest-probe", "User-Agent": "ShopApp-OnlineOrdersSync/1.0"},
            )
            urllib.request.urlopen(req, timeout=10)
            raise RuntimeError("expected the bot's sync endpoint to reject an unrecognized secret with 403")
        except urllib.error.HTTPError as e:
            if e.code != 403:
                raise RuntimeError(f"unexpected status from the bot's sync endpoint: {e.code}")
            https_check = "403 ok"
        except urllib.error.URLError as e:
            # urlopen wraps a TLS failure as URLError(reason=<ssl error>),
            # NOT a bare ssl.SSLCertVerificationError -- that exception
            # type never reaches this frame on its own, so checking for
            # it directly (an earlier version of this check did) would
            # silently never fire and this whole check would prove
            # nothing. The real signal is inside .reason.
            if isinstance(e.reason, ssl.SSLError):
                raise RuntimeError(f"HTTPS/TLS broken in this build (missing CA certs?): {e.reason}") from e
            https_check = "skipped (no network / Cloudflare unreachable right now)"

        window = MainWindow(conn)
        window.resize(1200, 780)
        window.show()
        app.processEvents()

        tabs = [
            ("dashboard", window.dashboard_page),
            ("products", window.products_page),
            ("customers", window.customers_page),
            ("invoices", window.invoices_page),
            ("supplier-invoices", window.supplier_invoices_page),
            ("online-orders", window.online_orders_page),
            ("settings", window.settings_page),
        ]
        for name, page in tabs:
            # indexOf(), not a hardcoded position: tab order in MainWindow
            # has already shifted once (dashboard inserted at 0) and will
            # again, so this loop shouldn't assume today's order.
            window._tabs.setCurrentIndex(window._tabs.indexOf(page))
            page.refresh()
            app.processEvents()
            window.grab().save(str(out_dir / f"tab-{name}.png"))

        # "Công nợ & Lợi nhuận" is no longer a tab (lần 19, request #3)
        # -- it's reachable only via the dashboard's "Chi tiết…" button,
        # which builds its own SummaryPage. Exercise/screenshot
        # window.summary_page directly instead of simulating that click.
        window.summary_page.refresh()
        window.summary_page.resize(768, 576)
        window.summary_page.show()
        app.processEvents()
        window.summary_page.grab().save(str(out_dir / "tab-summary.png"))
        window.summary_page.close()

        window.close()
    except Exception:
        result_path.write_text(f"FAIL:\n{traceback.format_exc()}", encoding="utf-8")
        return 1

    result_path.write_text(f"OK\nhttps_check: {https_check}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    main()
