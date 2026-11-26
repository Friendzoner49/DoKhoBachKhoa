-- 28/10/2026, giai doan kiem thu: AI doc anh hoa don NCC (shop.ocr.vision)
-- co the tra ve ten mat hang bang tieng Nga that (chu Kirin). raw_name
-- da co tu truoc (004_supplier_invoices.sql) nhung dang luu ten tieng Viet
-- khong dau nguoi dung tu go tay (vd "Bun Tuoi Ha Noi THANH LOC 500g"),
-- va bo so khop (supplier_aliases/suggest_matches) dang so tu theo kieu
-- Latin do -- ghi de bang chu Kirin vao raw_name se lam hong bo so khop
-- cu (khac bang chu cai hoan toan). raw_name_ru la cot RIENG, CHI DE
-- XEM/THAM KHAO: khong dung de so khop, khong thay the raw_name.
ALTER TABLE supplier_invoice_lines ADD COLUMN raw_name_ru TEXT;
