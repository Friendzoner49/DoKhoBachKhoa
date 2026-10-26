# Bot Telegram — chạy trên Cloudflare Workers (miễn phí, không cần máy chủ)

Bot này **tách biệt hoàn toàn** với app Python (`src/shop`) — không dùng chung
code, không bao giờ đọc `data/shop.sqlite`. Bot là kênh **nhận và chuyển tiếp
đơn hàng ĐƠN THUẦN** — không có menu riêng, việc chọn hàng luôn diễn ra trên
chính website.

**Từ lần cập nhật gần nhất (lần 12): có 2 cách khách gửi đơn tới bot:**

1. **Nhanh nhất — ngay trong Telegram (khuyên khách dùng cách này):** bot
   luôn hiện sẵn 1 nút "🛒 Đặt hàng" dưới khung chat. Khách bấm nút này →
   website mở ngay TRONG Telegram (gọi là "Mini App") → chọn hàng, bấm
   "Xác nhận gửi đơn" → đơn tự động bay thẳng tới bạn, khách **không cần gõ
   hay bấm Gửi gì thêm**. Lần đầu bot còn hỏi số điện thoại (hoặc bấm "Bỏ
   qua"); từ đơn thứ 2 trở đi bot nhớ luôn câu trả lời đó, không hỏi lại nữa.
2. **Cách cũ — mở website bằng trình duyệt thường** (khách không dùng
   Telegram để duyệt hàng, hoặc link Mini App vì lý do gì đó không mở được):
   chọn hàng xong bấm "Gửi đơn qua Telegram" → mở bot với nội dung đơn đã
   điền sẵn (`MÃ_HÀNG xSỐ_LƯỢNG — Tên` mỗi dòng) → khách vẫn phải tự bấm nút
   Gửi (➤) trong khung chat — đây là giới hạn của Telegram đối với link dạng
   này, không phải do mình cấu hình thiếu (xem mục "Vì sao vẫn còn bấm Gửi ở
   cách 2" bên dưới).

Cả 2 cách đều khớp mã hàng với
`https://friendzoner49.github.io/DoKhoBachKhoa/products.json`. Ai nhắn bất kỳ
thứ gì khác đều được mời bấm nút "🛒 Đặt hàng".

Vì sao Cloudflare Workers mà không phải 1 máy chủ ảo (VM): các cloud lớn của Mỹ (Oracle/Google/AWS/Azure) đều chặn/rủi ro với
tài khoản đăng ký từ Nga, còn Workers chạy "theo yêu cầu" (có tin nhắn tới mới
chạy), không có máy nào chạy 24/7 để bị thu hồi, và **không cần thẻ ngân
hàng** để tạo tài khoản miễn phí.

### Vì sao vẫn còn bấm Gửi ở cách 2

Telegram cố tình không cho bất kỳ link nào (kể cả link điền sẵn nội dung
tin nhắn) tự động bấm Gửi thay người dùng — đây là quy định chống spam ở
cấp nền tảng, không phải do bot thiếu cấu hình gì. Cách DUY NHẤT hợp lệ để
bỏ hẳn bước bấm Gửi là Mini App (cách 1) với `Telegram.WebApp.sendData()`,
và API đó CHỈ hoạt động khi Mini App được mở từ đúng 1 kiểu nút: nút
`web_app` gắn trong bàn phím tùy chỉnh của bot (chính là nút "🛒 Đặt hàng")
— không phải nút trong tin nhắn dạng inline, không phải Menu Button, không
phải link mở trực tiếp từ bên ngoài. Vì vậy cách 2 (mở website bằng trình
duyệt thường, không qua bot) không có cách nào khác ngoài link điền sẵn +
tự bấm Gửi.

## Cài đặt lần đầu (chỉ làm 1 lần)

### 1. Cài Node.js (nếu máy chưa có)

Máy Windows này đã có Node.js sẵn. Trên máy khác: tải bản LTS tại
https://nodejs.org — cài xong mở terminal mới, gõ `node -v` để kiểm tra. Chỉ
dùng để chạy `wrangler` (công cụ của Cloudflare) từ máy bạn — **sau khi
deploy xong, bot chạy hoàn toàn trên Cloudflare, không cần máy này mở hay cài
Node nữa.**

**Nếu dùng PowerShell** (mặc định trên Windows) và lệnh `npx` báo lỗi
`running scripts is disabled`: gõ `Get-ExecutionPolicy` để kiểm tra; nếu ra
`Restricted`, hãy mở **Command Prompt** (`cmd.exe`) thay vì PowerShell và
chạy lại các lệnh `npx ...` ở đó — không cần đổi cấu hình PowerShell.

### 2. Tạo tài khoản Cloudflare (miễn phí)

Vào https://dash.cloudflare.com/sign-up, đăng ký bằng email — không cần nhập
thẻ ngân hàng cho gói Workers miễn phí. **Nga đã chặn/làm chậm truy cập tới
Cloudflare từ giữa 2025** — nếu trang báo lỗi hoặc chậm bất thường, dùng VPN.
Lưu ý: VPN có thể cần dùng lại cho **mọi lệnh `wrangler` sau này** (`login`,
`deploy`, `secret put`, không chỉ lúc đăng ký), vì các lệnh này đều gọi tới
Cloudflare từ máy bạn. Bot chạy thật (khách bấm nút, đặt hàng) không bị ảnh
hưởng — đó là Cloudflare gọi Telegram từ máy chủ của Cloudflare, không qua
mạng Nga.

### 3. Cài công cụ dòng lệnh

Mở terminal tại đúng thư mục này (`K:\705bot\bot`):

```
npm install
npx wrangler login
```

Lệnh `login` sẽ mở trình duyệt để bạn đăng nhập/xác nhận — làm theo màn hình.

### 4. Tạo nơi lưu giỏ hàng (KV namespace)

```
npx wrangler kv namespace create CART_KV
```

Lệnh này in ra 1 dòng có `id = "xxxxxxxx"`. Mở file `wrangler.toml` trong
thư mục này, tìm dòng `id = "REPLACE_WITH_YOUR_KV_NAMESPACE_ID"` và dán đúng
id vừa in ra vào đó.

### 5. Tạo bot Telegram mới (nếu chưa có)

Mở Telegram, chat với **@BotFather**, gõ `/newbot`, đặt tên — BotFather trả
về 1 **token** dạng `123456:ABC-...`. **Lưu ý:** nếu bạn còn token bot cũ bị
lộ, hãy `/revoke` token đó trước, đừng dùng lại.

### 6. Cài 2 "bí mật" đầu tiên (chưa cài ADMIN_CHAT_ID vội)

```
npx wrangler secret put BOT_TOKEN
```
→ dán token bước 5 vào, Enter.

```
npx wrangler secret put WEBHOOK_SECRET
```
→ tự nghĩ ra 1 chuỗi ký tự ngẫu nhiên dài (vd chạy
`node -e "console.log(crypto.randomUUID())"` ở 1 terminal khác để tạo 1 chuỗi,
copy-paste vào). Đây là "mật khẩu" để Worker biết tin nhắn thật sự đến từ
Telegram, không phải ai đó giả mạo.

### 7. Deploy bot lên Cloudflare

```
npx wrangler deploy
```

Lệnh này in ra 1 URL dạng `https://705bot-telegram.<tên-bạn>.workers.dev` —
**lưu lại URL này**, dùng ở bước 8.

### 8. Gắn webhook — báo cho Telegram biết gửi tin nhắn tới đâu

Mở trình duyệt (Chrome/Edge), dán link sau vào thanh địa chỉ — thay `<TOKEN>`
= token bước 5, `<URL>` = URL bước 7, `<WEBHOOK_SECRET>` = chuỗi bước 6 —
rồi Enter (**không dùng `curl` trong PowerShell**, PowerShell biến `curl`
thành 1 lệnh khác và sẽ lỗi):

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<URL>&secret_token=<WEBHOOK_SECRET>
```

Trang trả về có `"ok":true` là thành công. (Chỉ cần làm 1 lần, trừ khi sau
này bạn deploy lại dưới 1 URL khác.)

### 9. Lấy ID Telegram của chính bạn (để bot biết gửi đơn hàng cho ai)

Mở Telegram, tìm chính bot bạn vừa tạo, bấm **Start**, gõ `/myid` — bot trả
lời 1 dãy số, đó là ID Telegram của bạn. Rồi chạy:

```
npx wrangler secret put ADMIN_CHAT_ID
```
→ dán dãy số đó vào. (Không cần deploy lại — secret có hiệu lực ngay.)

### 10. Cài secret để app máy tính đồng bộ đơn hàng online

App quản lý (trên máy tính) sẽ tự kéo danh sách đơn khách đặt qua bot về —
xem mục "Đồng bộ đơn hàng online vào app" bên dưới để hiểu vì sao. Cần 1
"mật khẩu" riêng (khác hẳn `WEBHOOK_SECRET`) để Worker biết đúng là app của
bạn đang hỏi, không phải ai khác:

```
npx wrangler secret put SYNC_SECRET
```
→ tự nghĩ ra 1 chuỗi ngẫu nhiên dài (giống cách tạo `WEBHOOK_SECRET` ở bước
6). **Dán đúng chuỗi này vào app** khi app hỏi "Worker URL" + "Mã đồng bộ"
lần đầu mở tab "Đơn hàng online" — xem hướng dẫn
trong chính app.

### 11. Đặt tên lệnh trong BotFather (để khách gõ `/` thấy gợi ý đúng)

Vẫn trong chat với @BotFather: `/setcommands`, chọn đúng bot, dán:

```
start - Đặt hàng qua website
contact - Liên hệ người bán
doisdt - Đổi số điện thoại đã lưu
xoatinnhan - Dọn bớt tin nhắn cũ (trong 48 giờ gần nhất)
```

### 12. Thử toàn bộ luồng

**Cách 1 (Mini App, trong Telegram):** mở chat với bot, bấm Start (bắt buộc
lần đầu, xem ghi chú bên dưới), bấm nút "🛒 Đặt hàng" hiện dưới khung chat —
website sẽ mở ngay trong Telegram. Thêm vài món, bấm "✅ Xác nhận gửi đơn".
Bot sẽ hỏi chia sẻ số điện thoại hoặc bấm "Bỏ qua, chỉ dùng Telegram" — chọn
1 trong 2. Bạn (admin) phải nhận được 1 tin nhắn đơn hàng từ chính bot. Đặt
thử đơn thứ 2: lần này bot KHÔNG hỏi lại số điện thoại nữa, đơn tới thẳng
bạn ngay. Muốn đổi lại số điện thoại đã lưu, gõ `/doisdt`.

**Cách 2 (link web cũ, ngoài Telegram):** mở website bằng trình duyệt
thường (không qua nút trong bot), thêm vài món, bấm "Gửi đơn qua Telegram" —
sẽ mở bot với nội dung đơn đã điền sẵn, phải tự bấm nút Gửi (➤).

Nếu không nhận được tin nhắn đơn hàng ở cách nào, kiểm tra lại bước 9 (phải
bấm Start với bot trước, Telegram không cho bot chủ động nhắn người chưa
từng bấm Start).

**Đã xác nhận (19/10/2026):** khách chưa từng bấm Start với bot bị Telegram
bắt bấm Start trước khi làm bất kỳ việc gì khác — đây là quy định chung của
Telegram cho mọi bot, áp dụng như nhau cho cả 2 cách trên, không phải lỗi
cấu hình. Chỉ cần bấm Start 1 lần duy nhất mỗi khách, không lặp lại ở các
đơn sau.

**Còn 1 điều chưa kiểm chứng được:** nút "🛒 Đặt hàng" dùng loại nút
`web_app` gắn thẳng vào tin nhắn (không phải Menu Button, không phải Mini
App đăng ký qua `/newapp`) — theo tài liệu Telegram, loại này không cần đăng
ký gì thêm với @BotFather ngoài các bước ở trên. Nếu sau khi deploy mà bấm
nút không mở được Mini App, hoặc bấm "Xác nhận gửi đơn" mà bot không nhận
được gì, đó là điều cần báo lại để kiểm tra thêm.

**Quan trọng — ĐỪNG cấu hình thêm Menu Button hay Mini App (`/newapp`,
`/setmenubutton`) trỏ về website, dù @BotFather có gợi ý:** `sendData()` —
cơ chế duy nhất giúp "Xác nhận gửi đơn" tự động gửi đơn — CHỈ hoạt động khi
Mini App được mở từ nút `web_app` gắn trong bàn phím tùy chỉnh (cách bot
đang dùng). Mở qua Menu Button hoặc link Mini App trực tiếp sẽ khiến
`sendData()` không làm gì cả, và vì trang đã xóa giỏ hàng trước khi gọi
`sendData()` (để tránh gửi nhầm giỏ cũ ở lần sau), khách sẽ mất luôn đơn mà
không có cảnh báo gì. Chỉ dùng đúng 1 cách duy nhất: nút trong bàn phím
tùy chỉnh mà bot tự gửi (đã có sẵn, không cần cấu hình thêm).

### 13. (Tùy chọn) Cài đồng bộ ảnh hóa đơn nhà cung cấp — lệnh `/hangve`

Tính năng này cho phép bạn chụp/gửi ảnh hóa đơn nhà cung cấp ngay trong
**1 group Telegram riêng** (vd group bạn đang dùng để quản lý channel báo
hàng về), rồi app trên máy tính tự kéo ảnh đó về để bạn đọc OCR + xác nhận
+ áp dụng giá — y hệt như bấm "Chọn ảnh…" trong app, chỉ khác là không cần
tự copy ảnh từ điện thoại sang máy tính nữa. Bỏ qua mục này nếu chưa cần.

Làm đúng thứ tự dưới đây (không đảo bước 5/6, xem lý do ở bước 6):

1. **Deploy bot trước** (nếu chưa deploy bản có tính năng này):
   ```
   npx wrangler deploy
   ```
2. **Thêm bot vào group đó** — mở group → Thêm thành viên → tìm đúng tên
   bot của bạn.
3. **Lấy ID của group đó:** trong group, gõ `/myid@BachHoa705_bot` (**phải
   ghi đủ tên bot sau `/myid`** — ở bước này "Group Privacy" chưa tắt nên
   Telegram chỉ chuyển cho bot những lệnh gõ RÕ RÀNG gửi cho đúng bot đó
   trong group, lệnh trần `/myid` có thể không tới nơi) — bot trả lời 1 số
   (số âm, vd `-1001234567890`, vì đây là group chứ không phải chat riêng).
4. Chạy:
   ```
   npx wrangler secret put SUPPLIER_GROUP_CHAT_ID
   ```
   → dán đúng số ở bước 3 vào (kể cả dấu `-` đầu số).
5. **Tắt "Group Privacy" cho bot** — bắt buộc, nếu không bot sẽ không nhận
   được ảnh bạn gửi trong BẤT KỲ group nào (đây là cài đặt chung của cả con
   bot, không phải riêng 1 group): mở chat với @BotFather → `/mybots` →
   chọn đúng bot → **Bot Settings** → **Group Privacy** → **Turn off**.
   (Dù tắt cho mọi group, code chỉ xử lý đúng ảnh kèm lệnh `/hangve` trong
   ĐÚNG group đã cài ở bước 4 — mọi group khác và mọi tin nhắn khác trong
   group đó đều bị bot im lặng bỏ qua, không trả lời gì.)
6. **Thêm lại bot vào group (xóa rồi thêm lại)** — Telegram chỉ áp dụng
   thay đổi Group Privacy cho **lần bot được thêm vào group kế tiếp**, nên
   nếu bot đã có sẵn trong group từ bước 2 (trước khi tắt privacy ở bước
   5), cần xóa bot khỏi group rồi thêm lại 1 lần nữa mới có hiệu lực.
7. **Thử ngay:** gửi 1 ảnh hóa đơn trong group, phần **chú thích (caption)**
   của ảnh gõ `/hangve` + ghi chú tùy ý, vd:
   ```
   /hangve đợt về 25/10, thiếu BUN01
   ```
   Phải thấy bot trả lời "Đã nhận ảnh hóa đơn ✅" ngay trong group. Không
   thấy gì → xem bảng "Sự cố thường gặp" ở README.md chính (gốc repo).

**Cách dùng hằng ngày:** gửi ảnh hóa đơn kèm `/hangve <ghi chú>` như bước 7.
Có thể gửi dạng **Ảnh** (Photo, nén nhẹ) hoặc dạng **File** (không nén, đọc
rõ hơn nếu cần OCR chính xác số) — cả 2 đều được nhận. Mở app trên máy tính
→ tab **Hóa đơn nhà cung cấp** → bấm **"🔄 Đồng bộ ảnh từ Telegram"** — hóa
đơn mới (có sẵn ảnh + ghi chú) hiện ra, mở lên đọc OCR/gõ tay/áp dụng giá
như bình thường. **Không có gì tự động ghi vào giá vốn** — luôn cần bạn tự
mở app và bấm "Áp dụng giá mới vào danh mục".
> Dùng chung Worker URL + Mã đồng bộ với tab "Đơn hàng online" (bước 10 ở
> trên) — không cần cài thêm gì trong app.

**Giới hạn cần biết:**
- Gửi NHIỀU ảnh cùng lúc (chọn nhiều ảnh rồi gửi 1 lần — Telegram gọi là
  album): chỉ ảnh ĐẦU TIÊN mang theo caption, các ảnh còn lại không có
  caption nên bị bỏ qua. Nếu cần nhiều ảnh cho 1 đợt hàng, gửi RIÊNG từng
  ảnh, mỗi ảnh kèm `/hangve` + ghi chú.
- Nếu group đó được Telegram tự nâng cấp lên "supergroup" (thường xảy ra
  khi group đông thành viên hoặc bật tính năng mới), **ID group sẽ đổi**
  (số bắt đầu bằng `-100`) — `SUPPLIER_GROUP_CHAT_ID` cũ sẽ không còn khớp
  nữa, bot im lặng không nhận ảnh. Gõ lại `/myid` trong group để lấy ID
  mới, chạy lại bước 4 với ID mới.

### 14. (Tùy chọn) Đăng mặt hàng theo mùa lên kênh — nút "📢 Đăng lên kênh"

Tính năng này cho app nút bấm 1 cú đăng ngay 1 mặt hàng (tên, giá, hạn bán,
ảnh) lên **kênh Telegram công khai** (vd "Đồ khô Bách Khoa") — dùng cho hàng
theo mùa chỉ mở bán vài ngày. Bỏ qua mục này nếu chưa cần.

1. **Deploy bot trước** (nếu chưa deploy bản có tính năng này — 1 lần
   `deploy` dùng chung cho cả mục 13 và mục 14 nếu bạn làm cả hai cùng lúc):
   ```
   npx wrangler deploy
   ```
2. **Thêm bot vào kênh làm Admin**, với quyền **"Post Messages"** (bắt
   buộc — nếu chỉ thêm làm thành viên thường hoặc thiếu đúng quyền này, bot
   sẽ không đăng được gì): mở kênh → Administrators → Add Administrator →
   tìm đúng tên bot của bạn → bật quyền "Post Messages".
3. **Lấy ID của kênh** — kênh KHÔNG nhận lệnh gõ trực tiếp như `/myid`
   (tin trong kênh không tới bot theo cách đó, và tự đăng `/myid` vào kênh
   sẽ làm phiền mọi người theo dõi kênh). Cách lấy ID riêng tư:
   - Mở 1 bài đăng bất kỳ trong kênh → **Forward** (chuyển tiếp) bài đó
     vào đúng chat riêng của bạn với bot (`@BachHoa705_bot`).
   - Bot trả lời ngay: `ID Telegram của kênh "Tên kênh": -100xxxxxxxxxx`.
   - Nếu kênh có **tên người dùng công khai** (vd kênh có link dạng
     `t.me/tenkenh`), bạn cũng có thể dùng thẳng `@tenkenh` thay cho số ID
     ở bước 4 — cách nào cũng được.
4. Chạy:
   ```
   npx wrangler secret put CHANNEL_CHAT_ID
   ```
   → dán số ID (kèm dấu `-` đầu số) hoặc `@tenkenh` vào.
5. **Thử ngay trong app:** tab "Danh mục hàng" → chọn 1 mặt hàng → bấm
   "📢 Đăng lên kênh" → xác nhận. Phải thấy tin mới xuất hiện trong kênh
   ngay sau đó.
   > **Lưu ý:** lần thử đầu tiên này đăng THẬT lên kênh, mọi người theo dõi
   > kênh đều thấy — nếu chỉ muốn thử nghiệm, xóa bài đăng đó ngay sau khi
   > xác nhận đã hoạt động (tự xóa bằng tay trong Telegram như xóa 1 tin
   > nhắn bình thường).

**Cách dùng hằng ngày:** thêm mặt hàng mới (hoặc sửa mặt hàng có sẵn) trong
app, tick "Sản phẩm theo mùa (có hạn bán)" + chọn ngày hết hạn, chọn ảnh →
bấm "Cập nhật website giá" (để mặt hàng lên web trước) → bấm "📢 Đăng lên
kênh". Ảnh được gửi kèm trực tiếp trong tin (không phụ thuộc website đã
publish xong hay chưa — chỉ cần ảnh đã chọn trong app). Qua ngày hết hạn,
website tự ẩn mặt hàng đó (không cần làm gì thêm); nút "📢 Đăng lên kênh"
vẫn dùng được cho mặt hàng bình thường (không có hạn bán) nếu muốn.
> Dùng chung Worker URL + Mã đồng bộ với tab "Đơn hàng online" (bước 10 ở
> trên) — không cần cài thêm gì trong app.

### 15. (Tùy chọn) Thông báo "hàng đã về" riêng từng khách

Tính năng này cho app gửi 1 tin nhắn Telegram **riêng tư** cho từng khách
(không phải đăng công khai như mục 14), báo đúng những món của họ đã về,
sau khi bạn nối 1 đợt đơn hàng online với (các) hóa đơn nhà cung cấp thật
sự giao hàng đợt đó. Bỏ qua mục này nếu chưa cần.

1. **Deploy bot trước** (nếu chưa deploy bản có tính năng này):
   ```
   npx wrangler deploy
   ```
2. Không cần secret mới — dùng chung `SYNC_SECRET` đã cài ở bước 10 (1
   credential cho "app nói chuyện với Worker").
3. **Thử ngay trong app:** tab "Đơn hàng online" → "Duyệt đợt hàng gần
   nhất…" → "Nối với hóa đơn NCC…" (chọn 1 hóa đơn đã nhập ở tab "Hóa đơn
   nhà cung cấp") → "📨 Kiểm tra & gửi thông báo khách hàng…".
   > **Lưu ý:** bước cuối gửi tin nhắn THẬT tới khách hàng, không thể thu
   > hồi — app sẽ hỏi xác nhận đúng số người trước khi gửi.

**Cách dùng hằng ngày:** chụp/nhận ảnh hóa đơn NCC như bình thường (tab
"Hóa đơn nhà cung cấp" hoặc `/hangve`, mục 13) → khớp đủ mã hàng/số lượng
→ sang tab "Đơn hàng online" → "Duyệt đợt hàng gần nhất…" → nối hóa đơn
vừa nhập với đúng đợt đơn khách tương ứng → bấm nút gửi thông báo. Nếu
hàng về thiếu/thừa so với tổng đã đặt, app tự mở màn hình để bạn chỉnh lại
từng đơn khách bị ảnh hưởng trước khi gửi.

## Dọn tin nhắn cũ (`/xoatinnhan`)

Telegram **giới hạn cứng**: bot chỉ được xóa tin nhắn (của bot lẫn của bạn)
trong vòng **48 giờ** kể từ lúc gửi — không có ngoại lệ, không có cách nào
vượt qua giới hạn này (đã tra cứu tài liệu chính thức của Telegram Bot API).

- Gõ `/xoatinnhan` trong chính chat của bạn với bot → bot xóa tất cả tin
  nhắn (đơn hàng chuyển tới bạn, các câu lệnh bạn gõ...) **còn nằm trong 48
  giờ gần nhất**. Chỉ hoạt động trong chat của chính bạn (ADMIN_CHAT_ID) —
  người khác gõ lệnh này trong chat của họ không có tác dụng gì.
- **Tin nhắn cũ hơn 48 giờ**, cách duy nhất là bạn tự làm trong Telegram,
  không cần code gì: mở chat với bot → bấm vào tên bot ở đầu trang → chọn
  **"Xóa lịch sử trò chuyện"** — không giới hạn thời gian, xóa được ngay.

## Đồng bộ đơn hàng online vào app quản lý

Từ giờ, mỗi đơn khách đặt qua bot (dù qua Mini App hay link web cũ) đều
được ghi lại **độc lập** với tin nhắn Telegram — kể cả khi tin nhắn gửi cho
bạn bị lỗi (vd bạn chưa bấm Start, mất mạng...), đơn vẫn không mất. Mở app
quản lý → tab **"Đơn hàng online"** → bấm **"Đồng bộ ngay"** để kéo danh
sách đơn mới về, xem tổng số lượng từng mặt hàng đang bị khách chờ (để biết
đợt tới cần nhập hàng gì), và bấm 1 nút để biến 1 đơn online thành hóa đơn
thật. Lần đầu dùng, app sẽ hỏi "Worker URL" (chính là URL ở bước 7) và "Mã
đồng bộ" (chuỗi bạn tạo ở bước 10) — dán vào 1 lần, app tự nhớ từ đó.

## Từ giờ về sau (không cần làm lại các bước trên)

- **Giá đổi trên web → bot tự thấy giá mới**, không cần làm gì thêm (bot đọc
  trực tiếp `products.json` mỗi khi có khách hỏi, Cloudflare tự cache ~5
  phút).
- **Nếu sửa code bot** (file nào trong `bot/src/`): chạy lại `npx wrangler
  deploy` — không cần làm lại các bước tạo tài khoản/secret/webhook.
- **Không có gì phải khởi động lại, không có máy nào phải để mở** — Cloudflare
  tự chạy bot 24/7.

## Chạy thử trên máy trước khi deploy thật (tùy chọn, cho người muốn kiểm tra kỹ)

```
npm test
```
chạy các bài test logic thuần (giỏ hàng, tìm kiếm, định dạng tin nhắn) —
không cần mạng, không cần tài khoản Cloudflare.

```
npx wrangler dev
```
chạy thử bot trên máy bạn với 1 URL tạm (cần `cloudflared` hoặc tương tự để
Telegram gọi tới được máy bạn) — bước này nâng cao, có thể bỏ qua và deploy
thẳng rồi test trên Telegram thật như bước 12.

## Giới hạn cần biết

- Gói miễn phí Cloudflare Workers: 100.000 tin nhắn/ngày, 1.000 lần
  ghi KV/ngày — dư thừa cho 1 shop nhỏ.
- Đơn đang chờ xác nhận SĐT lưu tối đa 1 ngày rồi tự xóa nếu khách không
  hoàn tất (tránh chiếm chỗ) — nếu khách bỏ dở quá lâu, chỉ cần bấm lại nút
  "🛒 Đặt hàng" hoặc "Gửi đơn qua Telegram" để gửi lại.
- Số điện thoại/lựa chọn "Bỏ qua" được nhớ **vĩnh viễn** theo từng khách
  (không tự hết hạn) — khách tự đổi lại bằng lệnh `/doisdt`.
- Mini App ("🛒 Đặt hàng") giới hạn 4096 ký tự cho 1 đơn — dư thừa cho 1
  đơn hộ gia đình bình thường; nếu khách cố tình đặt rất nhiều mặt hàng
  khác nhau trong 1 lần, trang sẽ báo và gợi ý dùng cách 2 (link web cũ).
- Bot không có menu/giỏ hàng riêng — nếu ai gõ gì đó không đúng định dạng
  đơn của website, bot chỉ mời họ bấm nút "🛒 Đặt hàng", không cố hiểu nội
  dung đó.
- Bản ghi đơn hàng online cho app đồng bộ tự xóa sau **90 ngày** (đủ thời
  gian để app lấy về; nếu app không mở máy trong 90 ngày liền, những đơn
  quá cũ sẽ không đồng bộ được nữa — hiếm khi xảy ra với việc dùng hàng
  ngày).
- `/xoatinnhan` chỉ xóa được tin nhắn trong 48 giờ gần nhất (giới hạn của
  Telegram, xem mục riêng ở trên) — tin cũ hơn phải tự xóa lịch sử trong
  Telegram.
- Mỗi lần khách hoàn tất 1 đơn giờ ghi tối đa 4 lần vào KV (đơn đang chờ,
  bản ghi đồng bộ cho app, lịch sử đặt hàng, SĐT/lựa chọn nhớ) thay vì 2
  như trước — vẫn rất dư so với giới hạn 1.000 lần ghi/ngày của gói miễn
  phí (đủ cho hàng trăm đơn/ngày).
- Gợi ý "Đặt lại đơn trước"/"★ Hay mua" (mục 7 lần 14) chỉ có từ đơn đầu
  tiên đặt SAU khi bot được cập nhật — không có dữ liệu cho các đơn cũ
  trước đó. Huy hiệu "★ Hay mua" chỉ hiện sau khi 1 mặt hàng xuất hiện
  trong **từ 2 đơn trở lên** của đúng khách đó (đơn đầu tiên chưa đủ để
  tính là "hay mua").
