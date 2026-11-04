-- Adds a per-product image filename, used by the public website. The
-- actual image files live in the site repo's images/ folder (not this
-- database) -- this column just records which filename (if any) to
-- serve for a product, so export_public can link to it.
ALTER TABLE products ADD COLUMN image_filename TEXT;
