-- Only one supplier exists in practice, so there is no suppliers table --
-- just the invoices themselves (one row per delivery/"dot hang") and
-- their line items as read off the photo. Matching a line to a catalog
-- product is recorded in supplier_invoice_lines.matched_code; once the
-- user confirms a match for a given raw name, it's remembered in
-- supplier_aliases so the next invoice from the same supplier matches
-- that item automatically.

CREATE TABLE supplier_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT,
    invoice_date TEXT,
    photo_filename TEXT, -- relative to data_dir()/supplier_invoices/
    total_amount INTEGER NOT NULL DEFAULT 0,
    paid INTEGER NOT NULL DEFAULT 0,
    applied_at TEXT, -- set once the user has pushed the cost changes into products
    created_at TEXT NOT NULL
);

CREATE TABLE supplier_invoice_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_invoice_id INTEGER NOT NULL REFERENCES supplier_invoices(id),
    raw_name TEXT NOT NULL,
    raw_qty REAL,
    raw_unit TEXT,
    raw_unit_price REAL,
    raw_line_total REAL,
    matched_code TEXT REFERENCES products(code),
    unit_conversion REAL NOT NULL DEFAULT 1, -- e.g. a case of 30 vs. catalog's per-piece cost
    cost_price_before REAL, -- product.cost_price at the moment this line was applied
    cost_price_after REAL, -- the per-catalog-unit price this line implies
    note TEXT
);

CREATE TABLE supplier_aliases (
    raw_name_normalized TEXT PRIMARY KEY,
    product_code TEXT NOT NULL REFERENCES products(code),
    unit_conversion REAL NOT NULL DEFAULT 1
);

CREATE INDEX idx_supplier_invoice_lines_invoice ON supplier_invoice_lines(supplier_invoice_id);

-- Re-importing the same delivery photo twice would otherwise double
-- "Bạn nợ nhà cung cấp" on the dashboard and double-log every price
-- change in price_history. NULL numbers (not yet typed in) are exempt --
-- SQLite's partial unique index already treats every NULL as distinct.
CREATE UNIQUE INDEX idx_supplier_invoices_number ON supplier_invoices(invoice_number) WHERE invoice_number IS NOT NULL;

-- 1 đợt hàng = 1 supplier invoice (confirmed with the user) -- adding this
-- now avoids a 005 migration later when customer invoices start linking
-- to the delivery they came from. Nullable: most invoices won't set it yet.
ALTER TABLE invoices ADD COLUMN supplier_invoice_id INTEGER REFERENCES supplier_invoices(id);
