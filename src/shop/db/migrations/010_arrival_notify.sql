-- Links a delivered supplier invoice back to the order batch it
-- fulfills, and tracks per-customer "hàng đã về" DM delivery -- see
-- shop.core.online_orders (linking/shortage) and
-- shop.core.arrival_notify (sending), request 25/10/2026.
--
-- Direction note: order_batches.supplier_invoice_id (007) was designed
-- assuming 1 batch <-> 1 invoice, but bot/README.md mục 13 tells the
-- owner to send one /hangve photo per message, so a single delivery
-- can arrive as SEVERAL supplier_invoices rows. The link has to allow
-- MANY invoices per batch, so it goes on supplier_invoices instead.
-- order_batches.supplier_invoice_id is left in place, unused, rather
-- than altered or dropped -- never edit an old migration.
ALTER TABLE supplier_invoices ADD COLUMN order_batch_id INTEGER REFERENCES order_batches(id);

-- Per customer ORDER, not per line: set only once the bot's Worker
-- confirms that chat_id's DM actually went out, so a retry after a
-- timeout/network failure never double-messages a real customer.
ALTER TABLE online_orders ADD COLUMN arrival_notified_at TEXT;

-- set_order_line_qty() overwrites `qty` with what actually arrived for
-- that customer -- original_qty preserves what they first ordered (set
-- only the FIRST time a line is adjusted), so the "hàng đã về" DM can
-- say "chỉ giao 3/5" instead of silently reporting the adjusted number
-- as if it were the original request.
ALTER TABLE online_order_lines ADD COLUMN original_qty REAL;
