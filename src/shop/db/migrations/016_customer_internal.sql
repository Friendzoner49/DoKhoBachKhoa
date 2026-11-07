-- "Dùng nội bộ": the owner's own purchases (priced at cost via markup 0, kept
-- out of debt/profit totals and the Công nợ & Lợi nhuận list/export).
ALTER TABLE customers ADD COLUMN internal INTEGER NOT NULL DEFAULT 0;
