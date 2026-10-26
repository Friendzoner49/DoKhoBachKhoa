-- Shared schema for the whole system: catalog import, invoice app, and
-- (later) the bot all read/write this same database.
--
-- cost_price stays REAL (some costs are per-kg fractions, e.g. 277.78).
-- Everything the customer sees or pays — unit_price, line_total,
-- opening_balance, payments — is stored as an INTEGER whole RUB amount,
-- computed with shop.core.pricing (Decimal, round-half-up) so totals
-- never drift from float rounding.
--
-- Invoice lines snapshot both cost and sale price at order time, so
-- historical debt/profit never move when the catalog price changes later.

CREATE TABLE products (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    unit TEXT,
    category TEXT,
    cost_price REAL NOT NULL DEFAULT 0,
    bulk_qty REAL NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    source_file TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT NOT NULL REFERENCES products(code),
    cost_price REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    source_file TEXT,
    note TEXT
);

-- default_markup_pct defaults to the public site markup (shop.core.pricing.
-- PUBLIC_MARKUP_PCT): a new customer should start at the public price, not
-- above it, until the owner sets a better (higher or lower) rate for them.
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    contact TEXT,
    default_markup_pct REAL NOT NULL DEFAULT 7,
    opening_balance INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    invoice_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft', -- draft | finalized | cancelled
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE invoice_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    product_code TEXT NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_snapshot TEXT,
    qty REAL NOT NULL,
    cost_price_snapshot REAL NOT NULL,
    unit_price INTEGER NOT NULL,
    line_total INTEGER NOT NULL,
    note TEXT
);

CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    amount INTEGER NOT NULL,
    paid_at TEXT NOT NULL,
    note TEXT
);

CREATE INDEX idx_invoices_customer ON invoices(customer_id);
CREATE INDEX idx_invoice_lines_invoice ON invoice_lines(invoice_id);
CREATE INDEX idx_payments_customer ON payments(customer_id);
CREATE INDEX idx_price_history_product ON price_history(product_code);
