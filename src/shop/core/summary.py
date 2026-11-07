"""Per-customer debt and profit. Only finalized invoices count: a draft
is work in progress and shouldn't show up as money owed yet.

debt_owed   = opening_balance + sum(finalized invoice totals) - sum(payments)
profit      = sum over finalized invoices in range of invoice_profit()
"""
import sqlite3

from shop.core.invoices import invoice_profit, list_invoices


def customer_debt(conn: sqlite3.Connection, customer_id: int) -> int:
    opening = conn.execute("SELECT opening_balance, internal FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if opening is None:
        raise ValueError(f"Unknown customer id: {customer_id}")
    if opening[1]:
        # "Dùng nội bộ" (the owner): always considered paid, never owes anything.
        return 0
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
        if not c["internal"]
    ]


def total_customer_debt(conn: sqlite3.Connection) -> int:
    """Sum of every customer's current debt -- what customers collectively
    owe the shop right now. Used for the big dashboard number."""
    from shop.core.customers import list_customers

    return sum(customer_debt(conn, c["id"]) for c in list_customers(conn, active_only=False) if not c["internal"])


def total_profit(conn: sqlite3.Connection, date_from: str | None = None, date_to: str | None = None) -> int:
    """Profit across every customer's finalized invoices in range."""
    from shop.core.customers import list_customers

    return sum(
        customer_profit(conn, c["id"], date_from=date_from, date_to=date_to)
        for c in list_customers(conn, active_only=False)
        if not c["internal"]
    )


def unpaid_invoices(conn: sqlite3.Connection, customer_id: int) -> list[dict]:
    """The customer's finalized invoices that still carry an unpaid amount, oldest
    first. Payments belong to the customer (not to one invoice), so they are
    allocated oldest-first: first against the opening balance, then invoice by
    invoice. `remaining` is what is still owed on that invoice (a partly paid one
    shows only its rest) -- lets the owner record "customer paid invoice #12"
    without typing odd amounts. An internal customer never owes anything."""
    row = conn.execute("SELECT opening_balance, internal FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if row is None or row[1]:
        return []
    pool = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE customer_id = ?", (customer_id,)).fetchone()[0]
    pool -= max(row[0], 0)  # payments settle the opening balance first
    out = []
    for invoice in sorted(list_invoices(conn, customer_id=customer_id, status="finalized"), key=lambda i: (i["invoice_date"], i["id"])):
        total = sum(
            r[0] for r in conn.execute("SELECT line_total FROM invoice_lines WHERE invoice_id = ?", (invoice["id"],))
        )
        covered = min(max(pool, 0), total)
        pool -= total
        if total - covered > 0:
            out.append({"id": invoice["id"], "invoice_date": invoice["invoice_date"], "total": total, "remaining": total - covered})
    return out
