-- 30/10/2026, lan 36: ten don vi dong goi lon (vd "thung", "tui", "bao")
-- cho mat hang co bulk_qty > 0, de ghep thanh dong van ban gui NCC
-- ("1 thung mi tom (30 goi)") thay vi chi hien so luong goi/kg le.
-- Rong ('') nghia la chua dat ten -- man hinh "Can nhap hang gi" se
-- fallback ve "kien" khi gap gia tri rong.
ALTER TABLE products ADD COLUMN bulk_unit TEXT NOT NULL DEFAULT '';
