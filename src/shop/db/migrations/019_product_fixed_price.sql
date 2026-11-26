-- Fixed SALE price per unit (RUB, the same for every customer) for pre-order dishes
-- the owner prices by sale price only, with no cost price (20/11/2026). NULL = use
-- the formula (shop.core.pricing.unit_price from cost_price and markup). Never
-- written by upsert_product, so price imports/supplier invoices cannot wipe it.
ALTER TABLE products ADD COLUMN fixed_price INTEGER;
