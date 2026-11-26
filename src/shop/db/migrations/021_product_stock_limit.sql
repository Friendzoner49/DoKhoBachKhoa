-- Limited portions for pre-order dishes (26/11/2026). stock_limit NULL = no
-- limit. stock_since = start of the current sale round (UTC ISO): only orders
-- and invoices from then on count against the limit. Written only by
-- shop.core.stock.set_stock_limit, so price imports cannot wipe them.
ALTER TABLE products ADD COLUMN stock_limit INTEGER;
ALTER TABLE products ADD COLUMN stock_since TEXT;
