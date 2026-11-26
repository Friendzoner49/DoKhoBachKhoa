import openpyxl

from shop.core.products import get_product
from shop.tools.import_xlsx import import_catalog


def _make_xlsx(tmp_path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BANG GIA HUP"
    ws.append(["ID", "TEN MAT HANG", "DON VI", "DON GIA GOC", "DON GIA HUP", "SLL", "GIA SLL", "TRANG THAI"])
    for row in rows:
        ws.append(row)
    path = tmp_path / "test.xlsx"
    wb.save(path)
    return path


def test_import_catalog_inserts_new_and_skips_existing_by_default(conn, tmp_path):
    xlsx = _make_xlsx(
        tmp_path,
        [
            ["X1", "San pham 1", "goi", 100, 110, 0, 0, True],
            ["X2", "San pham 2", "hop", 200, 220, 0, 0, True],
        ],
    )
    written, skipped = import_catalog(conn, xlsx)
    assert written == 2
    assert skipped == 0
    assert get_product(conn, "X1")["cost_price"] == 100

    # Re-import with a changed cost for X1: default (no --force) skips it,
    # so prices edited in the app since the first import survive.
    xlsx2 = _make_xlsx(tmp_path, [["X1", "San pham 1", "goi", 999, 1100, 0, 0, True]])
    written2, skipped2 = import_catalog(conn, xlsx2)
    assert written2 == 0
    assert skipped2 == 1
    assert get_product(conn, "X1")["cost_price"] == 100

    written3, skipped3 = import_catalog(conn, xlsx2, force=True)
    assert written3 == 1
    assert get_product(conn, "X1")["cost_price"] == 999
