-- Fixed whole-bag/case SALE price (RUB, for every customer) set by the owner as an
-- exception. NULL = use the formula (shop.core.pricing.bulk_price). Only meaningful
-- when bulk_qty > 0. Never written by upsert_product, so price imports/supplier
-- invoices cannot wipe it.
ALTER TABLE products ADD COLUMN bulk_price_override INTEGER;
