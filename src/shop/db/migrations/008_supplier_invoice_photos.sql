-- Supplier-invoice photos can now arrive straight from a Telegram
-- group command ("/hangve", lần 20) instead of only "Chọn ảnh…" by
-- hand -- see shop.core.supplier_invoices.sync_photos_from_bot. Each
-- synced photo becomes its own draft supplier_invoices row (the photo
-- + whatever caption note was sent), ready to open/OCR/match/apply
-- exactly like one entered by hand -- nothing here writes to products
-- automatically; "Áp dụng giá mới vào danh mục" still needs a human
-- to open the app and click it, same as every other supplier invoice.
ALTER TABLE supplier_invoices ADD COLUMN source_key TEXT;
ALTER TABLE supplier_invoices ADD COLUMN note TEXT;

-- Re-syncing (app reopened, cursor stale, etc.) must not create a
-- second draft for the same Telegram photo.
CREATE UNIQUE INDEX idx_supplier_invoices_source_key ON supplier_invoices(source_key) WHERE source_key IS NOT NULL;
