-- 02/11/2026, request: nhom hang "Qua tang" (vd Beluga vodka) can nhieu
-- anh (xem het cac goc chup) + mo ta chi tiet rieng, khac voi 146 mat
-- hang tap hoa thong thuong chi co 1 anh. gallery_filenames la mang
-- JSON ten file (vd '["QT001-g1.jpg","QT001-g2.jpg"]'), rong = '[]' --
-- khong dung cho san pham thong thuong. description rong ('') nghia la
-- chua co mo ta, website/bot chi hien khi khac rong.
ALTER TABLE products ADD COLUMN gallery_filenames TEXT NOT NULL DEFAULT '[]';
ALTER TABLE products ADD COLUMN description TEXT NOT NULL DEFAULT '';
