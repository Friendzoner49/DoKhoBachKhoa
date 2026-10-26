# Hướng dẫn sử dụng — Hệ thống bán hàng tạp hóa qua Telegram

Tài liệu này viết để **bạn tự đọc và tự dùng được ngay**, không cần biết lập
trình, không cần hỏi lại ai. Nếu sau này không còn nhờ Claude hỗ trợ nữa, đây
là nơi duy nhất bạn cần xem lại khi quên cách làm gì đó.

## Mục lục

1. [Hệ thống gồm những gì](#1-hệ-thống-gồm-những-gì)
2. [Mở app hằng ngày](#2-mở-app-hằng-ngày)
3. [Sao lưu dữ liệu — đọc trước khi làm gì khác](#3-sao-lưu-dữ-liệu--đọc-trước-khi-làm-gì-khác)
4. [Hướng dẫn từng tab trong app](#4-hướng-dẫn-từng-tab-trong-app)
5. [Cập nhật giá lên website cho khách xem](#5-cập-nhật-giá-lên-website-cho-khách-xem)
6. [Bot Telegram — nơi khách đặt hàng](#6-bot-telegram--nơi-khách-đặt-hàng)
7. [Đọc hóa đơn nhà cung cấp bằng OCR (tùy chọn)](#7-đọc-hóa-đơn-nhà-cung-cấp-bằng-ocr-tùy-chọn)
8. [Cài đặt trên máy mới / cài lại từ đầu](#8-cài-đặt-trên-máy-mới--cài-lại-từ-đầu)
9. [Sự cố thường gặp](#9-sự-cố-thường-gặp)

---

## 1. Hệ thống gồm những gì

```
App trên máy tính (Windows)  ──┬──  sổ sách thật: giá vốn, khách hàng, hóa đơn,
   "Quản lý bán hàng"           │    công nợ, lợi nhuận, hóa đơn nhà cung cấp
                                │
                                ├──▶ Website (friendzoner49.github.io/DoKhoBachKhoa)
                                │    — khách xem giá, đặt hàng. Chỉ hiển thị
                                │    giá công khai, KHÔNG chứa giá vốn/công nợ.
                                │
                                └──▶ Bot Telegram (@BachHoa705_bot)
                                     — khách đặt hàng qua đây, đơn tự động
                                     báo cho bạn và nạp vào app (tab
                                     "Đơn hàng online").
```

- **App trên máy tính là nơi DUY NHẤT sửa dữ liệu thật** (giá vốn, khách
  hàng, hóa đơn, công nợ). Website và bot chỉ đọc giá đã công khai, không
  bao giờ ghi ngược lại.
- **Dữ liệu thật nằm ở `K:\705bot\data`** trên máy này. Đừng xóa/di chuyển
  thư mục `K:\705bot` — app đã được cấu hình trỏ thẳng vào đó.
- Toàn bộ hệ thống **không tốn phí vận hành hằng tháng** (app chạy trên máy
  bạn, bot chạy miễn phí trên Cloudflare, website miễn phí trên GitHub
  Pages).

## 2. Mở app hằng ngày

File chạy app nằm ở:

```
K:\705bot\packaging\dist\BachHoa705\BachHoa705.exe
```

Nháy đúp vào `BachHoa705.exe` là mở được, không cần cài đặt gì thêm (Python,
thư viện... đều đã đóng gói sẵn bên trong).

**Mẹo:** chuột phải vào `BachHoa705.exe` → **Gửi tới → Màn hình nền (tạo lối
tắt)** để có icon mở nhanh trên Desktop, không cần mở lại đúng đường dẫn
này mỗi lần.

App mở ra sẽ có 7 tab ở trên cùng — xem chi tiết từng tab ở [mục 4](#4-hướng-dẫn-từng-tab-trong-app).

## 3. Sao lưu dữ liệu — đọc trước khi làm gì khác

- **Mỗi lần mở app, dữ liệu được tự động sao lưu** vào
  `%LOCALAPPDATA%\ShopApp\backups` (ổ C, không đồng bộ lên cloud nào), giữ
  lại **14 bản gần nhất**. Bạn không cần làm gì — việc này tự động.
- Muốn tự sao lưu tay thêm (ví dụ trước khi làm việc gì lớn): copy nguyên
  file `K:\705bot\data\shop.sqlite` ra chỗ khác (USB, Google Drive...).
- **Muốn khôi phục lại 1 bản sao lưu cũ:** đóng app lại, vào
  `%LOCALAPPDATA%\ShopApp\backups`, tìm file có ngày giờ muốn khôi phục,
  copy đè nó vào `K:\705bot\data\shop.sqlite` (đổi tên đúng thành
  `shop.sqlite`). Mở lại app là xong.
- **Đừng bao giờ xóa thư mục `K:\705bot\data`** — đó là toàn bộ sổ sách
  thật (khách hàng, hóa đơn, công nợ...), không khôi phục lại được nếu mất
  và không có sao lưu nào khác.

## 4. Hướng dẫn từng tab trong app

### Tổng quan

Mở app là thấy ngay tab này — 5 con số to:

- **Khách đang nợ bạn** / **Bạn nợ nhà cung cấp** — 2 số để biết ai đang nợ
  ai.
- **Chênh lệch** — dương nghĩa là khách nợ bạn nhiều hơn bạn nợ nhà cung
  cấp (có thể đòi khách trước); âm nghĩa là cần lo tiền cho nhà cung cấp
  trước.
- **Lợi nhuận tháng này** / **Lợi nhuận tất cả thời gian**.

Phía dưới có nút **📋 Chi tiết công nợ & lợi nhuận theo khách…** — mở ra
bảng công nợ + lợi nhuận TỪNG khách (trước đây là 1 tab riêng "Công nợ &
Lợi nhuận", giờ gom vào đây cho app bớt tab, bấm nút mới mở). Trong đó có
**Xuất Excel** để lưu/in báo cáo và **Làm mới** nếu vừa đổi gì ở tab khác
mà số chưa cập nhật.

### Danh mục hàng

Nơi quản lý toàn bộ mặt hàng (giá vốn, tên, đơn vị, nhóm hàng, ảnh, tình
trạng còn/hết hàng).

- **Thêm mặt hàng** — mở form nhập mã hàng, tên, đơn vị, giá vốn, nhóm
  hàng (gõ để chọn nhóm có sẵn hoặc gõ nhóm mới), giá sỉ (nếu có), ảnh (bấm
  "Chọn ảnh từ máy…" để chọn 1 ảnh — app tự resize, không cần chỉnh tay).
- **Sửa** — chọn 1 dòng trong bảng rồi bấm, sửa y hệt form thêm mới.
- **Ngừng bán / Mở bán lại** — dùng khi 1 mặt hàng **không bán nữa vĩnh
  viễn** (ẩn khỏi cả app lẫn website).
- **Hết hàng tạm thời / Còn hàng lại** — dùng khi mặt hàng **còn bán
  nhưng tạm thời chưa có hàng** (ví dụ hàng theo mùa) — vẫn hiện trên
  website với nhãn "Tạm hết hàng", khách vẫn thấy được nhưng không thêm vào
  giỏ được.
- **"Bán đến hết ngày" (trong form Thêm/Sửa)** — tick "Sản phẩm theo mùa
  (có hạn bán)" rồi chọn ngày, dùng cho hàng chỉ mở bán vài ngày (vd hàng
  đặc biệt số lượng hạn chế). Qua ngày đó, **website tự ẩn mặt hàng này**
  (không cần bấm gì thêm, không cần publish lại) — khác với "Hết hàng tạm
  thời" ở trên, cái này tự động theo ngày giờ đã đặt.
- **📢 Đăng lên kênh** — chọn 1 mặt hàng (nên là mặt hàng vừa đặt hạn bán ở
  trên) rồi bấm, app gửi tin kèm ảnh lên kênh Telegram công khai ngay lập
  tức — xem `bot/README.md` mục 14 để cài đặt lần đầu. Nên bấm "Cập nhật
  website giá" trước nếu đây là mặt hàng mới, để khách bấm vào tin xong đặt
  được hàng ngay.
- **Nhập danh mục từ Excel…** — chỉ cần dùng khi cài app lần đầu trên 1
  máy trống dữ liệu (xem [mục 8](#8-cài-đặt-trên-máy-mới--cài-lại-từ-đầu)).
  An toàn khi bấm nhầm: chỉ **thêm mới**, không ghi đè giá đã sửa trong
  app.
- **Xuất danh mục ra Excel** — lưu file `.xlsx` để xem/in, không ảnh
  hưởng dữ liệu trong app.
- **Cập nhật website giá** — xem [mục 5](#5-cập-nhật-giá-lên-website-cho-khách-xem).

### Khách hàng

- **Thêm khách hàng** — tên, địa chỉ, liên hệ, % markup riêng (mặc định
  7%, có thể để cao/thấp hơn cho từng khách), công nợ đầu kỳ nếu có.
- **Sửa** — chọn 1 khách rồi bấm.
- **Ngừng/Mở hoạt động** — ẩn khách không còn giao dịch nữa, không xóa dữ
  liệu cũ.
- **Ghi nhận thanh toán** — chọn khách, bấm, nhập số tiền khách vừa trả —
  công nợ của khách đó giảm ngay.
- **Lịch sử thanh toán** — xem lại/xóa các khoản thanh toán đã ghi nhận
  cho khách đó (xóa 1 khoản thì công nợ tăng lại đúng số đó).

### Hóa đơn

Đây là nơi tạo đơn bán hàng cho khách (ghi lại chi tiết từng mặt hàng đã
bán, tính công nợ + lợi nhuận).

1. **Tạo hóa đơn mới** → chọn khách hàng → mở ra màn hình soạn hóa đơn.
2. **Thêm dòng** → chọn mặt hàng → nhập số lượng. Giá vốn và đơn giá bán
   tự điền theo giá hiện tại trong danh mục + % markup của khách, nhưng
   **sửa tay được** (cột "Giá vốn"/"Đơn giá") nếu giá vừa đổi mà chưa kịp
   cập nhật trong danh mục.
3. Xong hết các dòng → **Hoàn tất hóa đơn** — từ lúc này, công nợ/lợi
   nhuận của hóa đơn này đã "chốt", đổi giá vốn trong danh mục sau đó
   KHÔNG làm thay đổi số đã chốt.
4. Muốn sửa lại hóa đơn đã hoàn tất → **Mở lại để sửa** → sửa xong lại
   **Hoàn tất hóa đơn** lần nữa.
5. **Hủy hóa đơn** — dùng khi khách hủy đơn, không xóa hẳn (vẫn xem lại
   được, không tính vào công nợ/lợi nhuận).
6. **Xóa hóa đơn nháp (trống)** — dọn các hóa đơn tạo nhầm, chưa có dòng
   hàng nào.
7. **Xuất Excel** — xuất hóa đơn ra file để gửi/in cho khách.

Ở tab **Hóa đơn** (danh sách), **Mở hóa đơn** để mở lại 1 hóa đơn đã tạo
trước đó.

**Thêm phí dịch vụ…** (trong màn hình sửa hóa đơn, cạnh "Thêm dòng") —
thêm 1 dòng KHÔNG phải mặt hàng trong danh mục, tự gõ tên + giá (vd "Phí
vận chuyển", "Phí đóng gói"). Giá tự gõ = 100% tính vào lợi nhuận (không
có giá vốn trừ đi), chỉ dùng được khi hóa đơn còn là nháp.

### Hóa đơn nhà cung cấp

Ghi lại từng đợt hàng nhập về — vừa để biết nợ nhà cung cấp bao nhiêu, vừa
để so sánh giá có tăng không và tự động cập nhật giá vốn trong danh mục.

1. **Nhập hóa đơn nhà cung cấp mới…** → mở ra màn hình nhập.
2. **Chọn ảnh…** để đưa ảnh đã chụp hóa đơn vào (có thể **Xoay 90°** nếu
   ảnh chụp bị lệch).
3. **Đọc chữ (OCR)** (cần cài Tesseract trước — xem [mục 7](#7-đọc-hóa-đơn-nhà-cung-cấp-bằng-ocr-tùy-chọn))
   — máy đọc chữ trong ảnh, hiện ra 1 ô bên cạnh để bạn **tham khảo khi tự
   gõ tay** vào bảng bên phải. Máy đọc có thể sai, nhất là số — luôn nhìn
   lại ảnh thật trước khi tin. **"Đọc chữ (OCR)" chỉ đọc tốt phần tiêu đề
   (số hóa đơn, ngày) — bảng mặt hàng trong ảnh hóa đơn kẻ ô gần như KHÔNG
   đọc được, cần tự nhìn ảnh gõ tay.**
   > **"Đọc bảng hàng (AI, chậm hơn)…"** (tùy chọn, cần cài thêm — xem
   > [mục 7](#7-đọc-hóa-đơn-nhà-cung-cấp-bằng-ocr-tùy-chọn)) — đọc được cả
   > bảng mặt hàng, không chỉ tiêu đề. Chậm hơn (15-30 giây/ảnh, app sẽ
   > không phản hồi trong lúc đó) và thử trên hóa đơn thật thì đa số đúng
   > nhưng không phải lúc nào cũng 100% — **vẫn chỉ là gợi ý đọc, luôn đối
   > chiếu với ảnh thật và tổng tiền in trên hóa đơn trước khi tin**.
4. Gõ từng dòng hàng vào bảng: tên trên hóa đơn, số lượng, đơn vị, đơn
   giá, **hệ số quy đổi** (quan trọng — nếu hóa đơn ghi giá theo "1 thùng
   = 30 gói", phải gõ 30 vào ô "Quy đổi" thì app mới tính đúng giá/gói,
   không thì sẽ hiểu nhầm giá tăng vọt).
   > **Thêm mặt hàng quen thuộc** — thay vì gõ tay từ đầu mỗi lần, bấm nút
   > này để hiện danh sách mặt hàng bạn đã từng khớp mã trước đây (mua
   > nhiều đợt nhất lên đầu) — tích vào đúng mặt hàng CÓ trong ảnh đang
   > xem, gõ lại số lượng cho khớp, rồi mới thêm vào bảng. Cột "Đơn giá"
   > luôn để trống, bắt bạn phải tự gõ theo đúng hóa đơn đang xem — giá
   > không bao giờ tự mang từ hóa đơn cũ sang.
5. **Gợi ý mã hàng cho dòng đang chọn** — app tự gợi ý mã hàng khớp trong
   danh mục dựa theo tên; bạn xác nhận lại (không tự động khớp, luôn cần
   bạn chọn).
6. Nhìn cột "Giá cũ/Giá mới/Δ%" để thấy trước giá sẽ đổi bao nhiêu % trước
   khi áp dụng.
7. **Áp dụng giá mới vào danh mục** — cập nhật giá vốn cho đúng các mã đã
   khớp. Hóa đơn áp dụng rồi, nếu áp dụng lại lần nữa sẽ được cảnh báo
   trước (tránh ghi đè nhầm giá mới hơn từ 1 đợt hàng khác).
8. **Đánh dấu ĐÃ thanh toán cho NCC** — khi đã trả tiền nhà cung cấp cho
   đợt hàng này (số "Bạn nợ nhà cung cấp" ở tab Tổng quan sẽ giảm theo).

**🔄 Đồng bộ ảnh từ Telegram** (tùy chọn, cần cài 1 lần — xem
`bot/README.md` mục 13) — nếu bạn gửi ảnh hóa đơn kèm lệnh `/hangve` trong
1 group Telegram riêng, bấm nút này để kéo ảnh đó về thành 1 hóa đơn mới
(có sẵn ảnh + cột "Ghi chú" lấy từ caption bạn gõ), rồi mở lên làm các bước
2-8 ở trên như bình thường. Không có gì tự động ghi vào giá vốn — phải tự
mở app và bấm "Áp dụng giá mới vào danh mục" mới có hiệu lực thật.

### Đơn hàng online

Đơn khách đặt qua bot Telegram hiện thẳng ở đây, không cần lướt tin nhắn
trong Telegram để tìm.

1. **Đồng bộ ngay** — kéo về các đơn mới khách vừa đặt (tự làm khi mở tab
   này lần đầu cũng được, nhưng bấm nút để chắc chắn có đơn mới nhất). Lần
   đầu dùng, cần bấm **Cài đặt đồng bộ…** nhập Worker URL + Mã đồng bộ 1
   lần duy nhất (xem `bot/README.md` để lấy 2 giá trị này — **máy này đã
   điền sẵn rồi**, chỉ cần làm lại nếu dùng app trên 1 máy khác).
2. **Cần nhập hàng gì?** — xem tổng số lượng từng mặt hàng ở các đơn
   **CHƯA chốt vào đợt nào** (mới đặt, đang chờ đợt tới) — chỉ để xem
   trước có gì đang tới, **không phải** danh sách thật sự cần đặt nhà
   cung cấp. Danh sách THẬT SỰ cần đặt (của đợt đã chốt, đã lọc bớt mặt
   hàng hết hàng) nằm ở **Duyệt đợt hàng gần nhất…** (xem bên dưới).
3. Chọn 1 đơn → **Tạo hóa đơn từ đơn này** → chọn khách hàng có sẵn (hoặc
   tạo khách mới ngay trong đó) → mở ra đúng màn hình sửa hóa đơn bình
   thường, giá tính theo giá **hiện tại** trong danh mục (không dùng giá
   bot ước tính lúc khách đặt, vì giá có thể đã đổi). Lần sau cùng khách
   đó đặt tiếp, app tự nhớ, chỉ hỏi xác nhận lại cho nhanh.
   > **Lưu ý quan trọng:** chỉ bấm nút này khi bạn **đã thật sự xử lý**
   > đơn đó — bấm xong, mặt hàng đó rút khỏi "Cần nhập hàng gì?" ngay, dù
   > hàng có thể chưa về từ nhà cung cấp.
4. Chọn 1 đơn → **Hủy đơn** — khi khách hủy/không liên lạc được.

**Chốt đợt hàng (mỗi ~2 tuần, hoặc khi bạn chuẩn bị nhập hàng):**

5. **📦 Chốt đợt hàng mới** — gộp mọi đơn "Chờ xử lý" chưa thuộc đợt nào
   thành 1 đợt (tự đồng bộ trước khi chốt, không cần tự bấm "Đồng bộ ngay"
   riêng). **Đơn khách đặt SAU khi chốt sẽ tự chờ đợt kế tiếp**, không bị
   gộp nhầm vào đợt vừa chốt.
6. **Duyệt đợt hàng gần nhất…** — mở bảng "Cần nhập hàng" của đợt vừa
   chốt. Mặt hàng nào nhà cung cấp **không có hàng**, chọn dòng đó rồi bấm
   **Loại mặt hàng này (hết hàng)** — mặt hàng đó bị bỏ khỏi **MỌI đơn**
   trong đợt cùng lúc (khách chỉ nhận + trả tiền phần còn lại, không cần
   sửa tay từng đơn một). Lỡ loại nhầm → chọn dòng đó ở bảng "Đã loại khỏi
   đợt này" rồi bấm **Khôi phục mặt hàng đã chọn**.
   > Cột **"Đợt"** trong bảng danh sách đơn cho biết đơn nào đã thuộc đợt
   > nào ("Chưa chốt đợt" = còn chờ lần chốt tiếp theo).

**Báo khách "hàng đã về" (sau khi hàng nhà cung cấp thật sự tới, cần cài
Worker riêng — xem `bot/README.md` mục 15):**

7. Trong "Duyệt đợt hàng gần nhất…", bấm **"Nối với hóa đơn NCC…"** — chọn
   1 hóa đơn đã nhập ở tab "Hóa đơn nhà cung cấp" (đã khớp đủ mã hàng/số
   lượng). 1 đợt có thể nối NHIỀU hóa đơn nếu hàng về qua nhiều lần chụp.
8. Bấm **"📨 Kiểm tra & gửi thông báo khách hàng…"**. Nếu hàng về **thiếu
   hoặc thừa** so với tổng khách đã đặt, app tự mở màn hình liệt kê từng
   mặt hàng chênh lệch — chọn 1 mặt hàng để xem từng đơn khách, **Sửa số
   lượng** hoặc **Loại / Khôi phục** riêng từng đơn (khác "Loại mặt hàng
   này" ở trên: ở đây chỉ ảnh hưởng 1 khách đang chọn, không phải cả đợt).
   Xong thì bấm "Xong" để tiếp tục.
9. App hỏi xác nhận số tin sẽ gửi rồi gửi **1 tin Telegram riêng cho từng
   khách** (không phải đăng công khai), chỉ liệt kê đúng món của người đó,
   không có giá/tổng tiền (giá chỉ chốt khi bạn thật sự tạo hóa đơn ở nút
   "Tạo hóa đơn từ đơn này"). Khách nào gửi không thành công (vd đã chặn
   bot) sẽ hiện trong danh sách "cần tự liên hệ" để bạn tự nhắn tay.

### Cài đặt

Nơi để 2 việc **không phải thao tác hằng ngày** — tách riêng khỏi các tab
khác để không bao giờ bị bấm nhầm trong lúc làm việc bình thường.

**Chuyển dữ liệu sang máy khác:**

- **Xuất dữ liệu ra file…** — gói toàn bộ dữ liệu (danh mục, khách hàng,
  hóa đơn, công nợ, ảnh hóa đơn nhà cung cấp) vào 1 file `.shopdata` duy
  nhất, chọn nơi lưu như lưu file bình thường. Chép file này sang máy
  khác bằng USB/Google Drive/AirDrop... tùy ý.
- **Nhập dữ liệu từ file…** — chọn file `.shopdata` vừa chép sang. App
  hiện rõ: dữ liệu đang có trên máy này vs. dữ liệu trong file sắp nhập
  (xuất lúc nào, từ máy nào), gõ đúng chữ xác nhận mới nhập được. **Nhập
  sẽ THAY THẾ TOÀN BỘ dữ liệu hiện tại trên máy này** (không gộp) — app
  tự sao lưu trước khi thay, rồi tự đóng lại; mở lại app để thấy dữ liệu
  mới.
- Dùng tính năng này để làm việc liền mạch giữa 2 máy (ví dụ Windows ở
  nhà và Mac khi ra ngoài) — xuất trên máy vừa dùng xong, nhập vào máy
  sắp dùng tiếp, **chỉ nên có 1 máy "đang dùng thật" tại 1 thời điểm**.

**Khôi phục cài đặt gốc:**

- Xóa vĩnh viễn khách hàng, hóa đơn, thanh toán, hóa đơn nhà cung cấp,
  đơn hàng online — dùng để dọn sạch dữ liệu bấm thử trước khi bắt đầu
  dùng thật cho khách. **Danh mục hàng (giá vốn, ảnh, nhóm hàng) được
  giữ nguyên**, không bị xóa.
  > Giá vốn đã đổi qua các lần "Áp dụng giá mới" (từ hóa đơn nhà cung
  > cấp) trong lúc dùng thử sẽ KHÔNG tự quay lại giá cũ — nếu cần, sửa
  > tay lại trong tab Danh mục hàng trước hoặc sau khi khôi phục.
- Phải gõ đúng chữ xác nhận mới xóa được (không chỉ bấm Yes/No) — tránh
  xóa nhầm. App tự sao lưu trước khi xóa.

## 5. Cập nhật giá lên website cho khách xem

Sau khi sửa giá/thêm mặt hàng/đổi ảnh trong tab **Danh mục hàng**, bấm
**Cập nhật website giá** ở chính tab đó. App tự đẩy giá mới lên
`https://friendzoner49.github.io/DoKhoBachKhoa/` — khách xem được ngay
(trong khoảng 1-2 phút, đôi khi tới 10 phút do GitHub Pages cần thời gian
cập nhật). Không cần làm gì thêm ở website — bấm xong là xong.

## 6. Bot Telegram — nơi khách đặt hàng

Bot `@BachHoa705_bot` là nơi khách chọn hàng (qua website mở ngay trong
Telegram) rồi gửi đơn tới bạn tự động. Hướng dẫn cài đặt chi tiết (1 lần
duy nhất, đã làm xong trên tài khoản Cloudflare/Telegram của bạn) nằm ở
**`bot/README.md`** — tài liệu này chỉ tóm tắt phần **dùng hằng ngày**:

- Mỗi đơn khách gửi sẽ tự động nhắn tới chat Telegram của bạn **và** nạp
  vào tab "Đơn hàng online" trong app — dù tin nhắn Telegram có gửi thành
  công hay không, đơn không bao giờ mất (xem [mục 4](#đơn-hàng-online)).
- **`/xoatinnhan`** — gõ lệnh này trong chính chat của bạn với bot để dọn
  bớt tin nhắn cũ (chỉ xóa được tin trong 48 giờ gần nhất — giới hạn của
  Telegram, không phải thiếu sót). Tin cũ hơn: bấm vào tên bot ở đầu
  trang chat → **"Xóa lịch sử trò chuyện"** — xóa hết, không giới hạn
  thời gian, không cần lệnh gì.
- Mỗi khách chỉ thấy đơn của chính họ — chat Telegram là riêng tư 1-1,
  không có cách nào khách xem được đơn của khách khác.
- Khách đặt lần 2 trở đi sẽ thấy gợi ý "Đặt lại đơn trước" và huy hiệu
  "★ Hay mua" ngay trên website — tự động, không cần bạn làm gì.
- Nếu khách muốn đổi lại số điện thoại đã lưu (hoặc đã bấm "Bỏ qua" lúc
  đầu, giờ muốn cho số), bảo khách gõ **`/doisdt`** trong chat với bot —
  lần đặt tiếp theo bot sẽ hỏi lại từ đầu.

## 7. Đọc hóa đơn nhà cung cấp bằng OCR (tùy chọn)

Nút "Đọc chữ (OCR)" ở tab **Hóa đơn nhà cung cấp** cần cài **Tesseract**
(phần mềm đọc chữ từ ảnh, miễn phí, chạy ngay trên máy — không gửi ảnh đi
đâu cả):

1. Tải tại: <https://github.com/UB-Mannheim/tesseract/wiki> (bản Windows,
   chọn file `.exe` mới nhất).
2. Cài như phần mềm bình thường (Next → Next → Install).
3. Mở lại app — nút "Đọc chữ (OCR)" sẽ dùng được ngay, không cần tải thêm
   dữ liệu ngôn ngữ (đã đóng gói sẵn trong app).

**Nếu chưa cài Tesseract, app vẫn chạy bình thường** — chỉ riêng nút này
báo lỗi rõ ràng bằng tiếng Việt, mọi việc khác (gõ tay vào bảng hóa đơn
NCC) vẫn dùng được 100%.

### Đọc bảng hàng bằng AI (tùy chọn, đọc tốt hơn Tesseract)

Nút **"Đọc bảng hàng (AI, chậm hơn)…"** dùng 1 model AI chạy ngay trên
máy (qua phần mềm **Ollama**, miễn phí, không gửi ảnh đi đâu cả, giống
tinh thần Tesseract) — đọc được cả bảng mặt hàng trong ảnh, không chỉ
phần tiêu đề như Tesseract. Cần cài thêm (1 lần):

1. Tải Ollama tại: <https://ollama.com> (bản Windows), cài như phần mềm
   bình thường.
2. Mở Ollama (chạy nền, có icon ở khay hệ thống).
3. Mở terminal/PowerShell, chạy: `ollama pull qwen2.5vl:7b` (tải khoảng
   6GB, chỉ cần 1 lần).
4. Mở lại app — nút "Đọc bảng hàng (AI)" sẽ dùng được ngay.

**Nếu chưa cài Ollama, app vẫn chạy bình thường** — chỉ riêng nút này báo
lỗi rõ ràng bằng tiếng Việt, mọi việc khác (OCR Tesseract, gõ tay) vẫn
dùng được 100%. Model này chạy chậm hơn Tesseract nhiều (15-30 giây/ảnh)
và **không phải lúc nào cũng đọc đúng 100%** — luôn đối chiếu kết quả với
ảnh thật và tổng tiền in trên hóa đơn trước khi gõ vào bảng, đừng tin
tuyệt đối.

## 8. Cài đặt trên máy mới / cài lại từ đầu

Chỉ cần làm phần này khi: đổi sang máy tính khác, cài lại Windows, hoặc
muốn dựng 1 bản chạy thử.

### Nếu đã có sẵn file `BachHoa705.exe` đã đóng gói (copy từ máy cũ)

Copy cả thư mục `BachHoa705` (chứa `BachHoa705.exe` và các file đi kèm) sang máy
mới, mở `BachHoa705.exe`. Lần đầu mở trên máy mới, app sẽ tự tạo dữ liệu
trống ở `Documents\ShopApp` — muốn dùng lại đúng dữ liệu cũ, xem phần
"Chuyển dữ liệu sang máy mới" bên dưới.

### Dùng trên Mac M2 (bản build sẵn qua GitHub Actions)

Máy phát triển này không có Mac để tự build/kiểm tra, nên bản Mac được
build **trên máy ảo của GitHub** (không cần Mac thật để ra file cài):

1. Vào `github.com/Friendzoner49/705bot` (đăng nhập đúng tài khoản GitHub
   được cấp quyền xem repo) → tab **Actions** → workflow **build** →
   nút **Run workflow** → **Run workflow** (nhánh `master`) → đợi khoảng
   5-10 phút tới khi thấy dấu ✓ xanh.
2. Bấm vào lần chạy vừa xong → cuối trang có mục **Artifacts** → tải
   `BachHoa705-mac` (file `.zip`, bên trong có file `.dmg`).
3. Giải nén, mở `.dmg`, kéo `BachHoa705.app` vào thư mục **Applications**.
4. **Lần đầu mở sẽ bị macOS chặn** (app build thủ công, chưa công chứng
   Apple) — mở **Terminal**, chạy:
   ```
   xattr -dr com.apple.quarantine /Applications/BachHoa705.app
   ```
   rồi nháy đúp mở lại `BachHoa705.app` bình thường.
5. Lần đầu mở, macOS hỏi quyền truy cập thư mục Documents — bấm **Cho
   phép**. Lỡ từ chối: **Cài đặt hệ thống → Quyền riêng tư & Bảo mật →
   Tệp & Thư mục** → bật lại quyền cho BachHoa705.
6. **Cần macOS 14 (Sonoma) trở lên** (kiểm tra:  → Giới thiệu về máy Mac
   này). M2 mua từ 2022 trở đi thường cập nhật lên được macOS 14/15 bình
   thường.
7. App mở lên lần đầu sẽ **trống dữ liệu** (máy mới) — xem mục 4, tab
   **Cài đặt → Nhập dữ liệu từ file…** để mang dữ liệu từ máy Windows
   sang (xuất từ Windows trước, chép file `.shopdata` sang Mac bằng
   AirDrop/Drive/USB, rồi nhập trên Mac).

**Khác biệt so với bản Windows:** nút "Cập nhật website giá" cần
`K:\705bot-site` (git repo kèm thông tin đăng nhập đã cấu hình sẵn) —
**chỉ dùng tính năng này từ máy Windows**, không cần làm trên Mac. Muốn
dùng OCR đọc hóa đơn NCC trên Mac: cài Homebrew (<https://brew.sh>) rồi
`brew install tesseract`.

> Workflow build Mac chưa từng chạy thử thật tính tới lúc viết phần này
> — nếu bước 1 báo lỗi (dấu ✗ đỏ), mở lần chạy đó, copy phần log bị đỏ
> lại để debug tiếp.

### Nếu cần tự đóng gói lại bản Windows từ code (khi code có cập nhật mới)

Cần máy đã cài sẵn `uv` (công cụ quản lý Python, tải tại
<https://astral.sh/uv>), rồi chạy đúng 1 lệnh từ thư mục gốc:

```
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

Script này tự chạy test, đóng gói, tự kiểm tra bản đóng gói
(`--self-test`), rồi nén thành `packaging\dist\BachHoa705-windows.zip`. Nếu
script dừng giữa chừng với dòng "Tests failed"/"Self-test failed", đọc
lại thông báo ngay phía trên dòng đó để biết lỗi gì.

### Chuyển dữ liệu (sổ sách thật) sang máy khác

Không cần sửa file tay nữa — xem mục 4, tab **Cài đặt**:

1. Trên máy đang có dữ liệu: **Xuất dữ liệu ra file…**, lưu file
   `.shopdata` ra USB/Drive/AirDrop...
2. Chép file đó sang máy kia, mở app, vào tab **Cài đặt → Nhập dữ liệu
   từ file…**, chọn đúng file vừa chép.
3. App hiện rõ dữ liệu 2 bên trước khi hỏi xác nhận — đọc kỹ rồi mới gõ
   chữ xác nhận. Xong, app tự đóng; mở lại là thấy dữ liệu mới.

## 9. Sự cố thường gặp

| Gặp phải | Cách xử lý |
|---|---|
| Mở app báo lỗi, hoặc số liệu trông sai lạ | Đóng app, khôi phục bản sao lưu gần nhất (xem [mục 3](#3-sao-lưu-dữ-liệu--đọc-trước-khi-làm-gì-khác)) |
| Nút "Đọc chữ (OCR)" báo lỗi | Chưa cài Tesseract — xem [mục 7](#7-đọc-hóa-đơn-nhà-cung-cấp-bằng-ocr-tùy-chọn). Mọi việc khác trong app vẫn dùng bình thường |
| Nút "Đọc bảng hàng (AI, chậm hơn)…" báo lỗi | Chưa cài Ollama, chưa mở Ollama (chạy nền), hoặc chưa `ollama pull qwen2.5vl:7b` — xem [mục 7](#7-đọc-hóa-đơn-nhà-cung-cấp-bằng-ocr-tùy-chọn). Mọi việc khác trong app vẫn dùng bình thường |
| "Cập nhật website giá" báo lỗi | Kiểm tra máy có đang nối mạng không; thử lại sau vài phút. Dữ liệu trong app không bị ảnh hưởng dù publish lỗi |
| "Đồng bộ ngay" (tab Đơn hàng online) báo lỗi | Kiểm tra mạng; nếu đang ở Nga có thể cần bật VPN. Đơn của khách không bị mất — bot vẫn giữ, đồng bộ lại sau vẫn lấy được |
| Gửi ảnh `/hangve` trong group nhưng app "Đồng bộ ảnh từ Telegram" không thấy gì mới | Kiểm tra theo đúng thứ tự: (1) đã tắt "Group Privacy" cho bot chưa (@BotFather → Bot Settings — cài đặt CHUNG của cả bot, không phải riêng 1 group); (2) đã **xóa rồi thêm lại bot vào group** sau khi tắt privacy chưa (Telegram chỉ áp dụng cho lần thêm TIẾP THEO, không hồi tố); (3) caption có bắt đầu đúng bằng `/hangve` không; (4) file gửi là Ảnh (Photo) hoặc File định dạng JPG/PNG — file HEIC (hay gặp khi gửi "Send as File" từ iPhone) bị từ chối, bot sẽ báo "Gửi dạng Ảnh"; (5) gửi đúng group đã cài `SUPPLIER_GROUP_CHAT_ID` chưa — group bị Telegram tự nâng cấp lên "supergroup" sẽ đổi ID, cần `/myid` lại. Xem `bot/README.md` mục 13 |
| Bấm "📢 Đăng lên kênh" báo lỗi | Kiểm tra: (1) đã cài `CHANNEL_CHAT_ID` chưa (`bot/README.md` mục 14); (2) bot còn quyền "Post Messages" trong kênh không (xem lại Administrators của kênh); (3) mặt hàng đã có ảnh chưa — chưa có ảnh thì không đăng được |
| Thấy 2 đơn giống hệt nhau trong "Đơn hàng online" | Hiếm khi xảy ra nếu lần gửi trước bị lỗi rồi khách gửi lại — bấm "Hủy đơn" cho bản thừa |
| Lỡ bấm "Khôi phục cài đặt gốc" hoặc "Nhập dữ liệu từ file" nhầm | Đóng app ngay, khôi phục bản sao lưu được tạo ngay TRƯỚC khi hành động đó chạy (xem [mục 3](#3-sao-lưu-dữ-liệu--đọc-trước-khi-làm-gì-khác)) |
| Bản Mac bị macOS chặn không mở được | Chạy `xattr -dr com.apple.quarantine /Applications/BachHoa705.app` trong Terminal — xem [mục 8](#8-cài-đặt-trên-máy-mới--cài-lại-từ-đầu) |
| Quên cách dùng 1 tính năng nào đó | Xem lại [mục 4](#4-hướng-dẫn-từng-tab-trong-app) ở trên, đúng tên nút đang thấy trong app |
| Cần biết thêm về cách bot hoạt động, cài đặt lại bot | Xem `bot/README.md` |
