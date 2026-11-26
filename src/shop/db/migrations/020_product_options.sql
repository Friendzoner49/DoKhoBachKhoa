-- Size options of one dish shown as ONE card on the web (20/11/2026): each
-- size stays its own product code (cart, bot, invoices keep working by code);
-- products sharing an option_group (e.g. "Bánh gối") merge on the web, and
-- option_label ("Set 3 chiếc") names the size. NULL = an ordinary product.
-- Never written by upsert_product, so price imports cannot wipe them.
ALTER TABLE products ADD COLUMN option_group TEXT;
ALTER TABLE products ADD COLUMN option_label TEXT;
