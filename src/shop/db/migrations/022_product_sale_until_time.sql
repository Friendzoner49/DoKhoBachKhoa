-- Order deadline down to the hour (26/11/2026): "HH:MM" in the shop computer's
-- local time, on the sale_until date. NULL = end of that day (23:59).
ALTER TABLE products ADD COLUMN sale_until_time TEXT;
