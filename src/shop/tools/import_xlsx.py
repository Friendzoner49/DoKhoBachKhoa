"""One-time import of the cost-price catalog from the shop's master Excel
file into the shared database.

Usage:
    uv run python -m shop.tools.import_xlsx "<path to bang gia do kho ...xlsx>" [--force]

Reads the "BANG GIA HUP" sheet's "DON GIA GOC" column (gia von / cost
price) — the sheet the shop actually keeps up to date (dated edit
notes). The "BANG GIA GOC" sheet is a stale older copy and is not used.

From now on, prices are edited in the invoice app, not in this file. By
default this script only INSERTS products that don't exist yet, so
re-running it (e.g. by habit, with an old file) never clobbers prices
edited in the app. Pass --force to also overwrite existing products.
"""
import sys
from pathlib import Path

import openpyxl

from shop.core.products import upsert_product
from shop.db.migrate import connect

SHEET_NAME = "BANG GIA HUP"


def read_rows(xlsx_path: Path):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2, values_only=True):
        # Columns: A code, B name, C unit, D cost (DON GIA GOC), E hup
        # price (+10%, not used as cost), F bulk qty (SLL), G bulk price
        # (GIA SLL - derived from the marked-up hup price, not a cost
        # figure, so not imported here), H active.
        code, name, unit, cost_price, _hup_price, bulk_qty, _bulk_sll_price, active = row[:8]
        if not code or not name:
            continue
        yield {
            "code": str(code).strip(),
            "name": str(name).strip(),
            "unit": (str(unit).strip() if unit else None),
            "cost_price": float(cost_price) if isinstance(cost_price, (int, float)) else 0.0,
            "bulk_qty": float(bulk_qty) if isinstance(bulk_qty, (int, float)) else 0.0,
            "active": active in (True, 1, "TRUE", "True"),
        }


def import_catalog(conn, xlsx_path: Path, force: bool = False) -> tuple[int, int]:
    """Import products from the shop's master Excel file. Returns
    (written, skipped). Used by the CLI below and by the app's "Nhap
    danh muc tu Excel..." button (for a fresh install / disaster
    recovery, e.g. a new Mac with an empty catalog)."""
    existing_codes = {row[0] for row in conn.execute("SELECT code FROM products")}

    written, skipped = 0, 0
    for item in read_rows(xlsx_path):
        if item["code"] in existing_codes and not force:
            skipped += 1
            continue
        upsert_product(conn, source=xlsx_path.name, **item)
        written += 1
    return written, skipped


def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)

    xlsx_path = Path(args[0])
    if not xlsx_path.exists():
        print(f"File not found: {xlsx_path}")
        sys.exit(1)

    conn = connect()
    written, skipped = import_catalog(conn, xlsx_path, force=force)

    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM products WHERE active = 1").fetchone()[0]
    print(f"Wrote {written} rows, skipped {skipped} already-existing rows (use --force to overwrite them).")
    print(f"Catalog now has {total} products ({active} active).")


if __name__ == "__main__":
    main()
