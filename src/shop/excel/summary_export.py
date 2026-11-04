"""Export a công nợ (debt) + lợi nhuận (profit) summary for all customers
to Excel."""
import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from shop.core.summary import customer_debt, customer_profit

HEADERS = ["Khách hàng", "Công nợ hiện tại (RUB)", "Lợi nhuận trong kỳ (RUB)"]


def export_summary(conn: sqlite3.Connection, out_path: Path, date_from: str | None = None, date_to: str | None = None) -> Path:
    from shop.core.customers import list_customers

    wb = Workbook()
    ws = wb.active
    ws.title = "Cong no - Loi nhuan"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for c in list_customers(conn, active_only=False):
        debt = customer_debt(conn, c["id"])
        profit = customer_profit(conn, c["id"], date_from, date_to)
        ws.append([c["name"], debt, profit])

    for col, width in zip("ABC", (30, 22, 22)):
        ws.column_dimensions[col].width = width

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
