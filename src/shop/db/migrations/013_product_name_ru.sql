-- 03/11/2026, request: ten tieng Nga chinh thuc cua tung mat hang (de
-- doi chieu voi "Ten tieng Nga (AI doc)" tung dong hoa don NCC khi hang
-- ve). Khac voi supplier_invoice_lines.raw_name_ru (migration 011, gan
-- voi TUNG DONG hoa don) -- day la 1 ten CHINH THUC gan voi san pham,
-- sua trong ProductDialog, mac dinh rong (dien dan qua cac don hang).
-- KHONG BAO GIO dua truong nay vao site/products.json (xem
-- shop.tools.export_public.build_payload -- build tung field 1, khong
-- dump nguyen dict nen them cot o day khong tu lo ra web).
ALTER TABLE products ADD COLUMN name_ru TEXT NOT NULL DEFAULT '';
