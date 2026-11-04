# Website tĩnh (`index.html`)

Trang bán hàng công khai, tĩnh hoàn toàn (không server riêng) — đọc đúng 1 file
dữ liệu (`products.json`) rồi tự vẽ giao diện bằng JavaScript thuần, không
framework, không build step. File này nằm trong repo chính (`K:\705bot`), là
**nguồn** — bản website thật khách xem được publish sang 1 repo GitHub **khác**
(`K:\705bot-site`, xem "Luồng dữ liệu" bên dưới), không sửa trực tiếp ở đó.

## Luồng dữ liệu — publish hoạt động thế nào

```
src/shop/site_template/index.html  (file này)
              │
              │  bấm "Cập nhật website giá" trong app, hoặc:
              │  uv run python -m shop.tools.publish_site
              ▼
  K:\705bot-site\index.html + products.json + images/
              │  (shop.tools.export_public xuất products.json
              │   từ data/shop.sqlite ngay trước bước publish)
              │  git add/commit/push
              ▼
  github.com/Friendzoner49/DoKhoBachKhoa (repo PUBLIC, nhánh main)
              │  GitHub Pages
              ▼
  https://friendzoner49.github.io/DoKhoBachKhoa/  (khách xem được ngay)
```

**Sửa `index.html` ở repo `K:\705bot-site` không có tác dụng lâu dài** — lần
publish tiếp theo sẽ ghi đè mất. Luôn sửa file này (`src/shop/site_template/
index.html`) trong repo chính, rồi publish lại.

`products.json` **không nằm trong repo chính** (gitignored, tự xuất mỗi lần
publish từ `data/shop.sqlite` — database thật). Muốn xem/test với dữ liệu thật
mà không publish thật, chạy:

```
uv run python -m shop.tools.export_public
```

lệnh này chỉ ghi ra `site/products.json` (local, gitignored), không đụng gì
tới `K:\705bot-site`/GitHub Pages.

## Test trước khi publish (bắt buộc — publish là lên thẳng production)

Mọi lần sửa `index.html`, test bằng trình duyệt thật (không phải tin vào mắt
đọc code) trước khi publish, vì nút "Cập nhật website giá" đẩy thẳng lên
production — không có môi trường staging:

```
uv run python -m shop.tools.export_public   # ra site/products.json từ DB thật
cd site && python -m http.server 8743        # phục vụ local
```

rồi mở `http://127.0.0.1:8743/index.html` bằng Edge/Chrome thật — kiểm tra
bằng mắt, và nếu cần lái qua nút bấm tự động thì dùng Edge headless +
`puppeteer-core` (cách các phiên làm việc trước đã dùng — xem
`CLAUDE_history.md`/`CLAUDE.md` mục 7 các lần sửa `index.html` để thấy ví dụ
script cụ thể). Luôn test ở độ rộng điện thoại (393px) **và** dark mode —
khách hàng chủ yếu mở từ điện thoại trong Mini App Telegram.

## Những hợp đồng KHÔNG được đổi tùy tiện

File này không chỉ phục vụ khách bấm mua — nó còn là nửa kia của 1 "hợp đồng
dữ liệu" với bot Telegram (`bot/`, xem `CLAUDE.md` mục 6). Đổi bất kỳ điều
nào dưới đây mà không sửa bot tương ứng sẽ làm hỏng luồng đặt hàng thật:

- **Định dạng dòng đơn `MÃ_HÀNG xSỐ_LƯỢNG — Tên`** (`buildOrderText()`) —
  bot (`bot/src/orderParser.js`) parse đúng định dạng này. Số lượng có thể
  là số thập phân (vd `x4.5`) từ 27/10/2026 — `parseCodeOrderLines`/
  `parseWebAppOrderLines` bên bot phải nhận đúng số lẻ, không được làm tròn.
- **Payload `Telegram.WebApp.sendData({lines:[{code,qty}]})`** — đây là cách
  DUY NHẤT Mini App gửi đơn tự động (không qua link điền sẵn). Đổi hình dạng
  payload phải sửa `parseWebAppOrderLines` bên bot cùng lúc.
- **`lineTotal(item, qty)` / `BULK_DISCOUNT_FACTOR`** — phải khớp 1-1 với
  `shop.core.pricing.bulk_discount` (Python) và `bot/src/cart.js`'s bản sao
  của cùng công thức. Sửa 1 nơi phải sửa cả 3 (xem lần 27/30 trong
  `CLAUDE_history.md`/`CLAUDE.md` để hiểu vì sao — chiết khấu chỉ áp dụng cho
  từng thùng/bao TRỌN VẸN, không phải cả số lượng).
- **Tham số URL `?last=`/`?top=`** (`parseLastOrderHint`) — bot
  (`bot/src/orderHistory.js`) gắn 2 tham số này vào nút "🛒 Đặt hàng" riêng
  cho từng khách. `qty` trong `?last=` có thể là số thập phân — dùng
  `parseFloat`, không `parseInt`.
- **Bộ đếm +/- sỉ** (`.item-bulk-stepper`/`#modal-bulk-stepper`) — cộng/trừ
  thẳng `item.bulk_qty` vào giỏ, không ghi đè. Chỉ hiện khi `item.bulk_qty >
  1` (không giới hạn số nguyên nữa từ 27/10/2026 — số lẻ đã an toàn end-to-end
  qua cả 2 parser của bot).
- **Lọc `sale_until`** — so theo NGÀY GIỜ ĐỊA PHƯƠNG của trình duyệt khách
  (`getFullYear()`/`getMonth()`/`getDate()`), không phải `toISOString()`
  (UTC) — Saint Petersburg là UTC+3, dùng UTC sẽ ẩn trễ ~3 tiếng mỗi ngày.
  Mặt hàng hết hạn bị LỌC HẲN khỏi `allItems` lúc tải `products.json`, không
  chỉ làm mờ đi.
- **`[hidden]` + CSS override cùng id** (vd `#reorder-btn[hidden]`,
  `#modal-stock-badge[hidden]`...) — 1 rule CSS theo id có `display` riêng sẽ
  thắng rule `[hidden]` mặc định của trình duyệt, nên mỗi phần tử ẩn/hiện có
  điều kiện cần 1 dòng `#id[hidden] { display: none; }` riêng. Quên dòng này
  là phần tử vẫn hiện dù đã set `hidden = true` trong JS.
- **`CATEGORY_ORDER`** — danh sách thứ tự nhóm hàng cố định; thêm nhóm mới
  (vd "Rượu", lần 19) phải thêm vào đây, không thì nhóm rơi xuống cuối trang
  không theo thứ tự mong muốn.
- **`SEARCH_SYNONYMS`** — bảng đồng nghĩa 2 chiều (`mỳ ↔ mì`, `nước tương ↔
  xì dầu`) dùng để tìm kiếm không phân biệt vùng miền. Bot KHÔNG có tính năng
  tìm kiếm riêng (đã bỏ hẳn, xem `CLAUDE.md` mục 6) nên bảng này chỉ cần sửa
  ở đây, không cần đồng bộ sang `bot/src/catalog.js`.

## Không có bộ test tự động cho file này

`index.html` không nằm trong `uv run pytest` hay `npm test` (JS thuần, không
qua build step để test được bằng Node dễ dàng) — `self_test()` của app chỉ
kiểm tra sơ bộ có chữ `"<html"`. **Luôn tự kiểm tra bằng trình duyệt thật**
(mục ở trên) trước khi publish, đây là lưới an toàn duy nhất.
