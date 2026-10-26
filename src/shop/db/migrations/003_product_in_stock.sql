-- Separate from `active` (= still a real catalog item at all, toggled by
-- "Ngung ban / Mo ban lai"): some items (fresh/seasonal goods like Ca Basa,
-- Ke Ga) come and go with the shipment, without ever being discontinued.
-- in_stock lets the website show "Tam het hang" instead of hiding the
-- item or treating it as gone for good.
ALTER TABLE products ADD COLUMN in_stock INTEGER NOT NULL DEFAULT 1;
