"""Per-customer debt and profit. Only finalized invoices count: a draft
is work in progress and shouldn't show up as money owed yet.

debt_owed   = opening_balance + sum(finalized invoice totals) - sum(payments)
profit      = sum over finalized invoices in range of invoice_profit()
"""
import sqlite3

from shop.core.invoices import invoice_profit, list_invoices


def customer_debt(conn: sqlite3.Connection, customer_id: int) -> int:
    opening = conn.execute("SELECT opening_balance FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if opening is None:
        raise ValueError(f"Unknown customer id: {customer_id}")
    opening_balance = opening[0]

    invoiced = conn.execute(
        """
        SELECT COALESCE(SUM(l.line_total), 0)
        FROM invoice_lines l
        JOIN invoices i ON i.id = l.invoice_id
        WHERE i.customer_id = ? AND i.status = 'finalized'
        """,
        (customer_id,),
    ).fetchone()[0]

    paid = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()[0]

    return opening_balance + invoiced - paid


def customer_profit(conn: sqlite3.Connection, customer_id: int, date_from: str | None = None, date_to: str | None = None) -> int:
    total = 0
    for invoice in list_invoices(conn, customer_id=customer_id, status="finalized"):
        if date_from and invoice["invoice_date"] < date_from:
            continue
        if date_to and invoice["invoice_date"] > date_to:
            continue
        total += invoice_profit(conn, invoice["id"])
    return total


def all_customers_debt(conn: sqlite3.Connection) -> list[dict]:
    from shop.core.customers import list_customers

    return [
        {**c, "debt": customer_debt(conn, c["id"])}
        for c in list_customers(conn, active_only=False)
    ]


def total_customer_debt(conn: sqlite3.Connection) -> int:
    """Sum of every customer's current debt -- what customers collectively
    owe the shop right now. Used for the big dashboard number."""
    from shop.core.customers import list_customers

    return sum(customer_debt(conn, c["id"]) for c in list_customers(conn, active_only=False))


def total_profit(conn: sqlite3.Connection, date_from: str | None = None, date_to: str | None = None) -> int:
    """Profit across every customer's finalized invoices in range."""
    from shop.core.customers import list_customers

    return sum(
        customer_profit(conn, c["id"], date_from=date_from, date_to=date_to)
        for c in list_customers(conn, active_only=False)
    )
