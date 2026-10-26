-- "Chốt đợt hàng" (lần 19, request #1 + #2): orders placed over up to
-- ~2 weeks are grouped into a batch when the owner closes it, so an
-- item the supplier doesn't have this round can be struck once for the
-- whole batch instead of per order, and orders synced after the cutoff
-- simply stay unbatched, waiting for the next close -- see
-- shop.core.online_orders.close_batch.
--
-- supplier_invoice_id is nullable and unused for now; added here so a
-- future "link this batch to the delivery it became" doesn't need yet
-- another migration (CLAUDE.md mục 3: 1 đợt hàng = 1 hóa đơn NCC).
CREATE TABLE order_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    closed_at TEXT NOT NULL,
    supplier_invoice_id INTEGER REFERENCES supplier_invoices(id)
);

ALTER TABLE online_orders ADD COLUMN batch_id INTEGER REFERENCES order_batches(id);

-- Soft-exclude, not DELETE: the owner needs the record of exactly which
-- item was struck from which order (to tell that customer, and in case
-- it was a misclick) -- see shop.core.online_orders.set_code_excluded.
ALTER TABLE online_order_lines ADD COLUMN excluded INTEGER NOT NULL DEFAULT 0;
