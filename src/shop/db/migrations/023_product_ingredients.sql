-- Ingredients of a pre-order dish (26/11/2026), shown on the web in a
-- "Thành phần" tab so customers can spot what they don't eat. '' = no tab.
ALTER TABLE products ADD COLUMN ingredients TEXT NOT NULL DEFAULT '';
