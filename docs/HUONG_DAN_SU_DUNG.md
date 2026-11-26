# Hướng dẫn sử dụng — Hệ thống bán hàng tạp hóa qua Telegram

Tài liệu này viết để **bạn tự đọc và tự dùng được ngay**, không cần biết lập
trình, không cần hỏi lại ai. Nếu sau này không còn nhờ Claude hỗ trợ nữa, đây
là nơi duy nhất bạn cần xem lại khi quên cách làm gì đó.

> Tài liệu này chỉ tập trung vào **cách dùng hằng ngày**. Muốn hiểu kiến trúc
> hệ thống hoặc đóng góp code, xem [README.md](../README.md) ở thư mục gốc.

## Mục lục

1. [Hệ thống gồm những gì](#1-hệ-thống-gồm-những-gì)
2. [Mở app hằng ngày](#2-mở-app-hằng-ngày)
3. [Sao lưu dữ liệu — đọc trước khi làm gì khác](#3-sao-lưu-dữ-liệu--đọc-trước-khi-làm-gì-khác)
4. [Hướng dẫn từng tab trong app](#4-hướng-dẫn-từng-tab-trong-app)
5. [Cập nhật giá lên website cho khách xem](#5-cập-nhật-giá-lên-website-cho-khách-xem)
6. [Bot Telegram — nơi khách đặt hàng](#6-bot-telegram--nơi-khách-đặt-hàng)
7. [Đọc hóa đơn nhà cung cấp bằng AI (tùy chọn)](#7-đọc-hóa-đơn-nhà-cung-cấp-bằng-ai-tùy-chọn)
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
- **Muốn khôi phục lại 1 bản sao lưu cũ (vd lỡ thao tác nhầm):** mở app, vào
  tab **Cài đặt → Khôi phục từ bản sao lưu**, chọn đúng bản theo ngày giờ,
  bấm **Khôi phục…**. App tự đóng, mở lại là thấy dữ liệu đã khôi phục.
  **Lưu ý:** mọi thay đổi làm SAU thời điểm bản sao lưu đó (không riêng
  thao tác nhầm gần nhất) sẽ mất — chọn đúng bản gần thời điểm xảy ra lỗi
  nhất có thể.
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

- **Chọn "Loại hàng" ở đầu form Thêm/Sửa:** **🍜 Món đặt trước** (chọn sẵn
  khi thêm mới) hoặc **🛒 Đồ khô, tạp hoá**. Form chỉ hiện các ô của loại đó:
  món đặt trước có Giá bán, Hạn đặt, Số suất, Tên món chung, Tên cỡ, Thành
  phần; đồ khô có Nhóm hàng, giá sỉ, đơn vị đóng gói lớn, tên tiếng Nga. **Thêm
  đồ khô thì nhớ đổi sang "Đồ khô, tạp hoá" trước.** Màn hình thấp thì cuộn
  chuột để xem hết các ô.
- **Thêm mặt hàng** — mở form nhập mã hàng, tên, đơn vị, giá vốn, nhóm
  hàng (gõ để chọn nhóm có sẵn hoặc gõ nhóm mới), giá sỉ (nếu có), ảnh (bấm
  "Chọn ảnh từ máy…" để chọn 1 ảnh — app tự resize, không cần chỉnh tay).
  - **"Tên đơn vị đóng gói lớn"** (cạnh "Số lượng sỉ") — chỉ cần điền cho
    mặt hàng có giá sỉ (vd "thùng" cho mì tôm 30 gói/thùng, "túi" cho gạo
    4,5kg/túi). Dùng để ghép thành câu gửi nhà cung cấp ở "Cần nhập hàng
    gì?" (tab Đơn hàng online) — không ảnh hưởng tới giá bán cho khách.
  - **"Tên tiếng Nga"** — để trống, điền dần qua từng đợt hàng khi đối
    chiếu với tên AI đọc được trên ảnh hóa đơn NCC (cột "Tên tiếng Nga (AI
    đọc)" trong dialog Hóa đơn nhà cung cấp). Chỉ hiện trong app, **không
    bao giờ** lên website.
  - **"Mô tả chi tiết"** (khung "Giới thiệu món") **+ "Bộ sưu tập ảnh"** (chỉ cần cho mặt hàng đặc biệt,
    vd nhóm "Quà tặng") — mô tả dài hiện dưới tên mặt hàng khi khách bấm
    xem chi tiết; bộ sưu tập là NHIỀU ảnh (ngoài "Ảnh sản phẩm" chính) để
    khách xem hết các góc chụp, bấm "Thêm ảnh vào bộ sưu tập…" chọn nhiều
    ảnh cùng lúc, chọn 1 ảnh trong khung rồi bấm "Xóa ảnh đã chọn" để bỏ.
    Để trống cả hai nếu mặt hàng không cần giới thiệu dài — không ảnh
    hưởng gì tới các mặt hàng tạp hóa thường.
- **"Thành phần" (cho món đặt trước)** — trong form Thêm/Sửa, ở khung
  "Giới thiệu món", bấm tab "Thành phần" và ghi món gồm những gì, mỗi thành
  phần 1 dòng. Trên website, cửa sổ món có thêm tab **"Thành phần"** cạnh
  "Mô tả" để khách biết trước món có gia vị mình không ăn. Dưới danh sách
  của món đặt trước, web tự ghi một dòng nhỏ mời khách nhắn shop nếu muốn
  thay đổi nguyên liệu. Để trống thì
  không hiện tab. Món nhiều cỡ: chỉ cần ghi ở cỡ rẻ nhất. Ghi xong bấm
  "Cập nhật website giá".
- **Thứ tự bảng:** món đặt trước luôn nằm trên, đồ khô nằm dưới (mặc định
  xếp theo tên); trong mỗi nhóm, món khách đang đặt được nằm trên, món hết
  hạn / hết suất / tạm hết / ngừng bán nằm dưới. Bấm vào tiêu đề cột bất kỳ ở dòng đầu để xếp lại theo cột
  đó, bấm lần nữa để đảo ngược; món đặt trước vẫn ở trên.
- **Sửa** — chọn 1 dòng trong bảng rồi bấm, sửa y hệt form thêm mới. Bấm
  **đúp 2 lần** vào 1 dòng bất kỳ cũng mở form này, không cần chọn dòng
  trước.
- **Ô chọn trạng thái (3 nấc) + nút "Áp dụng"** — chọn 1 dòng trong bảng,
  chọn 1 trong 3 trạng thái rồi bấm Áp dụng:
  - **Đang bán** — bình thường, hiện đầy đủ ở app và website.
  - **Tạm hết hàng** — còn bán nhưng tạm thời chưa có hàng (ví dụ hàng
    về chậm) — vẫn hiện trên website với nhãn "Tạm hết hàng", khách
    thấy được nhưng không thêm vào giỏ được.
  - **Ngừng bán** — không bán nữa vĩnh viễn, ẩn khỏi cả app lẫn website.
- **"Món ăn đặt trước" (trong form Thêm/Sửa)** — dùng cho món nấu theo
  đợt (cơm tấm, bánh mì pate, bún chả…): chọn loại "🍜 Món đặt trước" rồi chọn **ngày cuối cùng nhận đặt**. Nên thêm ảnh món và điền ô
  "Mô tả chi tiết" (khách bấm vào món mới thấy mô tả) và tab "Thành phần"
  nếu muốn khách biết món có gì. Đơn vị nên ghi
  "suất", "ổ", "hộp".
  - Trên website, món này hiện ở tab riêng **"🍜 Món ăn đặt trước"**, ảnh
    to, tên nổi bật, kèm nhãn "Hạn đặt T4, 18/11" (ngày cuối cùng thì
    "Hạn đặt hôm nay"). Khi còn món đặt được, website mở thẳng vào tab này;
    đồ khô nằm ở tab "🛒 Đồ khô, tạp hóa" bên cạnh. Chưa có món nào thì
    website không hiện tab, trông như cũ.
  - **Qua hạn đặt**, món tự chuyển sang màu xám "Hết hạn đặt" (vẫn thấy ảnh
    và tên, khách không đặt được nữa) và **tự ẩn sau 7 ngày** — không cần
    bấm gì, không cần cập nhật lại website. Muốn ẩn ngay thì chọn "Ngừng
    bán" rồi bấm "Cập nhật website giá".
  - Món đã đủ suất trước hạn: chọn "Tạm hết hàng" → website ghi "Hết suất".
  - **Nút "Ẩn món hết hạn đặt…"** (dòng thứ 2 của tab Danh mục hàng): liệt
    kê các món đã qua hạn mà web còn hiện, tick món muốn ẩn → app chuyển các
    món đó sang "Ngừng bán" và hỏi có cập nhật website ngay không. Món không
    tick vẫn hiện xám tới hết 7 ngày. Lần sau nấu lại món cũ: xem các bước
    "Tuần sau nấu lại món cũ" ở dưới.
  - **Ô "Luôn hiện tab "Món ăn đặt trước" trên web"**: bỏ tick (mặc định) thì
    tab chỉ hiện khi có món; tick thì tab luôn hiện, lúc chưa có món ghi
    "Hiện chưa có món nào đang nhận đặt…". Đổi xong bấm "Cập nhật website
    giá".
  - **Món nhiều cỡ (set 3 / set 5…): trên web chỉ hiện 1 món, khách tự chọn
    cỡ.** Trong app, mỗi cỡ vẫn là 1 dòng mã hàng riêng (đơn, hoá đơn và lãi
    lỗ tính theo từng cỡ), chỉ cần gõ **cùng một "Tên món chung (gộp cỡ)"**
    và **"Tên cỡ"** riêng cho từng dòng. Đang có: `BGOI03` "Set 3 chiếc" +
    `BGOI05` "Set 5 chiếc" (tên món chung "Bánh gối"); `CGA010` "Set 10 chân"
    + `CGA015` "Set 15 chân" (tên món chung "Chân gà").
    - Web hiện 1 thẻ "Bánh gối · 350 – 550 ₽", nút **Chọn cỡ**. Bấm vào thấy
      mỗi cỡ một dòng có nút − / +, khách chọn số lượng **nhiều cỡ trong 1
      lần** (vd 25 chân = 1 set 15 + 1 set 10; 8 bánh = 1 set 5 + 1 set 3),
      xem tổng tiền rồi bấm "Thêm vào giỏ hàng". Mở lại món là sửa số lượng
      đã chọn, không bị cộng gấp đôi. Tìm "bánh gối" cũng chỉ ra 1 món.
    - Mô tả trong cửa sổ món lấy của cỡ rẻ nhất, nên mô tả cỡ đó nên viết
      chung cho cả món (vd "Chân gà kèm sốt chấm chua cay").
    - **Ảnh chính và bộ sưu tập ảnh trên web lấy từ cỡ rẻ nhất** (vd
      `BGOI03`): đổi ảnh thì đổi ở dòng đó.
    - Tên món chung phải gõ giống hệt nhau (ô này có danh sách sẵn để chọn).
      Gõ khác một chữ là web tách thành 2 món.
  - **Giá của món đặt trước: gõ thẳng 2 con số, app không tự tính gì thêm.**
    - Ô **"Giá bán (món đặt trước)"**: giá khách trả, ví dụ 350. Web, tin
      đăng kênh và hoá đơn của mọi khách đều dùng đúng số này, không cộng
      % markup.
    - Ô **"Giá vốn"**: tiền vốn thật của 1 set, ví dụ bánh gối 28 ₽/chiếc
      nên set 3 chiếc = 84. Số này chỉ dùng để tính lãi/lỗ ở phần Lợi nhuận.
    - Giá đang dùng: `BGOI03` 350 (vốn 84), `BGOI05` 550 (vốn 140), `CGA010`
      300 (vốn 70), `CGA015` 420 (vốn 105).
    - Vốn thay đổi thì sửa ô "Giá vốn" **trước khi** lập hoá đơn cho khách.
      Hoá đơn đã lập mà còn nháp thì vẫn sửa được cột "Giá vốn" ngay trên
      hoá đơn. Hoá đơn đã chốt thì giữ nguyên giá vốn lúc chốt.
    - Khách "Dùng nội bộ" lấy món thì chỉ trả giá vốn.
    - Đổi loại sang "Đồ khô, tạp hoá" rồi bấm OK là **xoá luôn giá bán, hạn
      đặt, số suất, tên món chung và thành phần**: món quay về tính giá như
      hàng thường (giá vốn + 7%).
    - **Gộp đơn:** đơn khách đặt món qua bot cũng vào đợt như hàng thường.
      Tab Đơn online → **📦 Chốt đợt hàng mới** → **Duyệt đợt hàng gần
      nhất…** sẽ thấy tổng số
      set phải làm của từng món. Món tự nấu không bị báo "thiếu hàng" vì
      không có hoá đơn nhà cung cấp.
  - **Tuần sau nấu lại món cũ (làm theo thứ tự):**
    1. Tab Danh mục hàng → tích "Hiện cả mặt hàng đã ẩn/ngừng bán" → tìm
       các dòng theo mã hàng (`BGOI03`, `BGOI05`, `CGA010`, `CGA015`).
    2. Món nào đã "Ngừng bán": chọn dòng → chọn **Đang bán** → **Áp dụng**.
    3. Bấm đúp vào dòng → đổi **ngày cuối nhận đặt** → OK. Đổi giá khách
       trả thì sửa ô "Giá bán (món đặt trước)"; vốn đổi thì sửa ô "Giá vốn";
       đổi ảnh nếu cần. Làm lần lượt cho từng set.
    4. Bấm **Cập nhật website giá** → mở web xem lại tab "🍜 Món ăn đặt trước".
    5. Chọn 1 dòng bất kỳ của món → **📢 Đăng lên kênh**. Món nhiều cỡ chỉ
       đăng **1 tin** gồm ảnh, tên món, giá từng cỡ, hạn đặt và link web.
       Món đã đăng tuần trước thì app hỏi lại "ĐÃ đăng lên kênh lúc…" → bấm
       **Yes** để đăng tin mới. Không cần đăng thêm cho cỡ còn lại.
  - **Hạn đặt theo giờ:** cạnh ngày "Hạn đặt" có ô giờ (sau chữ "lúc"), vd
    20:00, tính theo giờ máy tính của bạn. Để 23:59 = nhận đến hết ngày. Đổi
    xong bấm **Cập nhật website giá**. Đến giờ, web tự chuyển "Hết hạn đặt" và
    bot từ chối đơn gửi muộn (cả đơn). **Đổi hoặc gia hạn giờ chốt trước giờ
    cũ ít nhất 15 phút**: web và bot giữ bản giá cũ thêm vài phút.
  - **Món có số suất giới hạn (vd chỉ nấu 8 suất xôi xéo):** bấm đúp vào món
    → loại "🍜 Món đặt trước" → ô **"Số suất có hạn"** gõ TỔNG số suất mở bán
    (8) → OK → **Cập nhật website giá**. Để "— (không giới hạn)" nếu không cần.
    - Web hiện "Còn 6 suất", không cho chọn quá; hết thì hiện "Hết suất". Bot
      không nhận đơn vượt số còn lại và báo khách (cả đơn bị từ chối, kể cả
      hàng khác đi kèm). Bot tự trừ khi có đơn (có thể trễ khoảng 1 phút).
    - Số trên web chỉ chắc chắn mới sau khi bấm "Đồng bộ ngay" rồi "Cập nhật
      website giá": khách không vào được bot qua mạng của họ (thiếu VPN) sẽ
      thấy số lúc cập nhật gần nhất. Bot vẫn chặn đơn vượt số.
    - App đếm đơn online và hoá đơn gõ tay tính từ 0 giờ ngày bật. Cột "Tình
      trạng" hiện "Còn 6/8 suất" (bấm "Đồng bộ ngay" ở tab Đơn hàng online để
      app lấy đơn mới).
    - Khách đặt miệng, không qua bot: lập hoá đơn cho khách đó, hoặc giảm ô
      "Số suất có hạn". Rồi **Cập nhật website giá**.
    - Huỷ đơn hoặc bớt món: bấm **Cập nhật website giá** để web và bot trả
      suất lại.
    - Tuần sau mở lại món đã hết hạn với hạn mới: app đếm lại từ đầu.
    - Hai khách bấm đặt gần như cùng lúc vẫn có thể vượt 1–2 suất, nên xem lại
      đơn trước khi nấu.
  - **Món mới hoàn toàn**: bấm **Thêm mặt hàng** → mã hàng (vd `BMI001`),
    tên ghi cả cỡ set, Đơn vị "set", Giá vốn = tiền vốn thật 1 set, loại
    "🍜 Món đặt trước" + chọn ngày, gõ Giá bán, Mô tả ghi set gồm những gì (nguyên liệu, gia vị ghi ở tab "Thành phần"),
    chọn ảnh chính (ảnh ngang đẹp nhất, web cắt khung 16:9) và thêm ảnh vào
    bộ sưu tập → OK. Món có nhiều cỡ: thêm mỗi cỡ 1 mặt hàng, cùng "Tên món
    chung", mỗi cỡ một "Tên cỡ" (ảnh chỉ cần ở cỡ rẻ nhất) → làm tiếp bước
    4–5 ở trên.
- **Nút video cuối trang web** (vlog, giải bóng, sự kiện cộng đồng): tab
  **Cài đặt → Sửa nút video…**, dán nguyên bài đăng như trong group. Dòng đầu
  không có link là tiêu đề khối; mỗi dòng có link (`https://…`) thành 1 nút,
  phần chữ còn lại là tên nút; các dòng khác (lời cảm ơn…) bị bỏ qua. Thêm sự
  kiện mới: thêm 1 dòng "Tên (link)" rồi bấm "Cập nhật website giá". Để trống
  thì web không hiện khối này. Trên web, các link gom thành **1 nhóm thu gọn**
  ở cuối trang chủ (logo YouTube + tiêu đề, phần "(…)" cuối tiêu đề không hiện);
  khách bấm vào nhóm mới thấy các nút nhỏ, bấm nút mới mở YouTube.
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
- **Sửa** — chọn 1 khách rồi bấm. Tích **"Dùng nội bộ (chính tôi)"** cho
  khách là chính bạn: hóa đơn lấy giá gốc (markup 0%), và khách này **không
  tính vào công nợ, lợi nhuận, Tổng quan**, không hiện trong Công nợ & Lợi nhuận, và luôn được coi là ĐÃ thanh toán (công nợ hiện 0, không cần "Ghi nhận thanh toán").
- **Ngừng/Mở hoạt động** — ẩn khách không còn giao dịch nữa, không xóa dữ
  liệu cũ.
- **🗑 Xóa khách hàng** — chỉ xóa được khách **chưa có hóa đơn/thanh toán
  nào** (khách mới thêm nhầm, gõ sai tên...). Khách đã có lịch sử giao
  dịch sẽ bị chặn xóa, app báo lỗi gợi ý dùng "Ngừng hoạt động" thay vào
  đó — để không bao giờ mất dữ liệu công nợ/lợi nhuận cũ.
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
6. **🗑 Xóa hóa đơn** — xóa hẳn hóa đơn **nháp hoặc đã hủy** (dọn hóa đơn
   tạo nhầm, có dòng hàng hay không cũng xóa được). Hóa đơn **đã hoàn
   tất thì không xóa được** (nút tự mờ đi) — muốn bỏ thì "Hủy hóa đơn"
   trước, không xóa trực tiếp, để không bao giờ mất dấu 1 giao dịch đã
   chốt công nợ/lợi nhuận.
7. **Xuất Excel** — xuất hóa đơn ra file để gửi/in cho khách.

Ở tab **Hóa đơn** (danh sách), **Mở hóa đơn** để mở lại 1 hóa đơn đã tạo
trước đó.

**📨 Gửi hóa đơn cho khách (Telegram):** chọn 1 hóa đơn **đã hoàn tất** rồi bấm
nút này — app gửi bản tóm tắt bằng chữ (các dòng hàng, tổng tiền, công nợ hiện
tại) cho đúng khách đó qua bot. Khách phải đã liên kết Telegram (tự có khi bạn
tạo hóa đơn từ đơn online của khách đó). Có hỏi xác nhận trước khi gửi; cột
"Đã gửi Telegram" cho biết hóa đơn nào đã gửi, gửi lại sẽ có cảnh báo. Dùng
chung "Cài đặt đồng bộ…" của tab Đơn hàng online, không cần cài thêm gì.
Cuối tin có phần **💳 Chuyển khoản** (số điện thoại, ngân hàng) ngay trước câu
cảm ơn — nhập/sửa ở tab **Cài đặt → Thông tin chuyển khoản…** (mỗi dòng 1 thông
tin; để trống thì không in). Thông tin này chỉ lưu trên máy bạn, không nằm trong code.
Muốn tự liên kết (hoặc đổi/gỡ) Telegram của khách: tab **Khách hàng** → chọn khách →
**🔗 Liên kết Telegram…** → tích các chat thuộc về khách đó (chat đang gắn khách khác
sẽ chuyển sang khách này). Danh sách lấy từ các chat đã từng đặt đơn qua bot, nên
cần "Đồng bộ từ Telegram" trước.
Khách chưa liên kết bot: bấm **📋 Copy nội dung hóa đơn** rồi dán (Ctrl+V) vào
Zalo/Telegram gửi tay cho khách.

**Ghi nhận thanh toán theo hóa đơn:** ở tab Khách hàng, chọn khách → "Ghi nhận
thanh toán". Hộp thoại liệt kê các hóa đơn khách còn nợ (tiền đã trả được trừ
dần từ hóa đơn cũ nhất); **tích đúng hóa đơn khách vừa trả** thì số tiền và ghi
chú tự điền, không phải gõ số lẻ. Có thêm nút "Trả hết công nợ". Số tiền vẫn
sửa tay được.

**Thêm phí / giảm giá…** (trong màn hình sửa hóa đơn, cạnh "Thêm dòng") —
thêm 1 dòng KHÔNG phải mặt hàng trong danh mục, tự gõ tên + giá (vd "Phí
vận chuyển", "Giảm giá khách quen"). **Muốn giảm giá thì gõ đơn giá số ÂM**
(vd -100). Giá tự gõ = 100% tính vào lợi nhuận (không có giá vốn trừ đi),
chỉ dùng được khi hóa đơn còn là nháp.
Khi hóa đơn còn nháp, bấm đúp vào **tên, đơn vị, số lượng, giá vốn, đơn giá**
của bất kỳ dòng nào để sửa (vd đổi tên dòng thành "Ưu đãi sinh nhật"); sửa
chỉ áp cho hóa đơn này, không đổi danh mục hàng.

**Chiết khấu sỉ tự động:** mặt hàng có "Số lượng sỉ" (xem mục Danh mục
hàng) mà số lượng trên dòng hóa đơn đạt tới mức đó sẽ tự có thêm 1 dòng
"Chiết khấu sỉ 2% — ..." ngay bên dưới, trừ đúng số tiền đã quảng cáo
trên website. Dòng này tự thêm/xóa lại mỗi khi bạn sửa số lượng của
dòng hàng chính, không cần tự tính tay.

**Giá sỉ ngoại lệ:** mặc định giá cả bao/thùng = giá lẻ × số lượng × 0,98.
Muốn giá khác cho 1 mặt hàng: Danh mục hàng → bấm đúp mặt hàng → tích
**"Thêm ngoại lệ giá sỉ"** và gõ giá BÁN cả bao/thùng (cố định, mọi khách như
nhau). Bỏ tích để về công thức. Giá này dùng cho hóa đơn, website, bot và Excel;
**phải bấm "Cập nhật website giá" và deploy lại bot** thì khách mới thấy. Không
bao giờ tính cao hơn giá lẻ × số lượng. Khách "Dùng nội bộ" không có chiết
khấu sỉ (đúng giá gốc).

### Hóa đơn nhà cung cấp

**🗑 Xóa hóa đơn (cả đơn nháp):** nút ngay cạnh "Đồng bộ từ Telegram". Chọn 1
hóa đơn (nhìn cột "#") rồi bấm nút này (có hỏi xác nhận). Chỉ xóa
hóa đơn và các dòng của nó; giá vốn đã áp dụng vào danh mục vẫn giữ nguyên, file
ảnh/PDF gốc vẫn còn trong thư mục dữ liệu. Hóa đơn lấy từ Telegram đã xóa sẽ
không bị kéo về lại ở lần "Đồng bộ từ Telegram" sau.

Ghi lại từng đợt hàng nhập về — vừa để biết nợ nhà cung cấp bao nhiêu, vừa
để so sánh giá có tăng không và tự động cập nhật giá vốn trong danh mục.

1. **Nhập hóa đơn nhà cung cấp mới…** → mở ra màn hình nhập. Hóa đơn chưa
   áp dụng giá (nháp) khi mở ra mà còn trống thì **Số hóa đơn** tự điền số tiếp
   theo sau hóa đơn đã áp dụng giá gần nhất (vd. đã có 1, 2 → điền 3), **Ngày** tự
   điền hôm nay; sửa tay được như bình thường.
2. **Chọn ảnh…** để đưa ảnh đã chụp hóa đơn vào (có thể **Xoay 90°** nếu
   ảnh chụp bị lệch).
3. **Đọc bảng hàng (AI)…** (cần cài Ollama trước — xem [mục 7](#7-đọc-hóa-đơn-nhà-cung-cấp-bằng-ai-tùy-chọn))
   — AI đọc cả bảng mặt hàng trong ảnh, hiện ra 1 ô bên cạnh để bạn
   **tham khảo khi tự gõ tay** vào bảng bên phải. Chậm (15-30 giây/ảnh,
   hóa đơn dài 20-50 dòng có thể 1-3 phút; app sẽ không phản hồi trong lúc đó) và thử trên hóa đơn thật thì đa số
   đúng nhưng không phải lúc nào cũng 100% — **vẫn chỉ là gợi ý đọc, luôn
   đối chiếu với ảnh thật và tổng tiền in trên hóa đơn trước khi tin**.
4. Gõ từng dòng hàng vào bảng: tên trên hóa đơn, số lượng, đơn vị, đơn
   giá, **hệ số quy đổi** (quan trọng — nếu hóa đơn ghi giá theo "1 thùng
   = 30 gói", phải gõ 30 vào ô "Quy đổi" thì app mới tính đúng giá/gói,
   không thì sẽ hiểu nhầm giá tăng vọt). **Giá sỉ cả bao** (vd. bao gạo 5kg
   giá 1400₽, danh mục tính theo kg): bấm **"Tự quy đổi giá sỉ"** — app tự điền
   Quy đổi = 5 cho các dòng đã khớp mã mà giá hóa đơn rõ ràng là giá cả bao,
   để so với giá/kg trong danh mục. Dòng bạn đã tự sửa Quy đổi thì giữ nguyên.
   > **Thêm mặt hàng quen thuộc** — thay vì gõ tay từ đầu mỗi lần, bấm nút
   > này để hiện danh sách mặt hàng bạn đã từng khớp mã trước đây (mua
   > nhiều đợt nhất lên đầu) — tích vào đúng mặt hàng CÓ trong ảnh đang
   > xem, gõ lại số lượng cho khớp, rồi mới thêm vào bảng. Cột "Đơn giá"
   > luôn để trống, bắt bạn phải tự gõ theo đúng hóa đơn đang xem — giá
   > không bao giờ tự mang từ hóa đơn cũ sang.
5. **Gợi ý mã hàng cho dòng đang chọn** — app tự gợi ý mã hàng khớp trong
   danh mục dựa theo tên; bạn xác nhận lại (không tự động khớp, luôn cần
   bạn chọn). Không có gợi ý nào gần giống thì app mở thẳng bảng tìm theo
   tên/mã để bạn tự chọn.
6. Nhìn cột "Giá cũ/Giá mới/Δ%" để thấy trước giá sẽ đổi bao nhiêu % trước
   khi áp dụng.
7. **Áp dụng giá mới vào danh mục** — cập nhật giá vốn cho đúng các mã đã
   khớp. Hóa đơn áp dụng rồi, nếu áp dụng lại lần nữa sẽ được cảnh báo
   trước (tránh ghi đè nhầm giá mới hơn từ 1 đợt hàng khác).
8. **Đánh dấu ĐÃ thanh toán cho NCC** — khi đã trả tiền nhà cung cấp cho
   đợt hàng này (số "Bạn nợ nhà cung cấp" ở tab Tổng quan sẽ giảm theo).

**🔄 Đồng bộ từ Telegram** (tùy chọn, cần cài 1 lần — xem
`bot/README.md` mục 13) — nếu bạn gửi ảnh hóa đơn kèm lệnh `/hangve` trong
1 group Telegram riêng, bấm nút này để kéo ảnh đó về thành 1 hóa đơn mới
(có sẵn ảnh + cột "Ghi chú" lấy từ caption bạn gõ), rồi mở lên làm các bước
2-8 ở trên như bình thường. Không có gì tự động ghi vào giá vốn — phải tự
mở app và bấm "Áp dụng giá mới vào danh mục" mới có hiệu lực thật.

**Gửi file PDF scan** (cũng kèm `/hangve`): bot nhận PDF; khi bạn bấm "Đồng bộ
ảnh từ Telegram", app đổi trang 1 thành ảnh, giữ nguyên file PDF gốc, và **gửi
lại ảnh nét (dạng file, không bị nén) vào đúng group đó** để bạn lưu vào album.
Ảnh nét chỉ về sau khi bạn mở app và bấm đồng bộ — bot không tự đổi PDF được.
PDF nhiều trang chỉ lấy trang 1.

### Đơn hàng online

Đơn khách đặt qua bot Telegram hiện thẳng ở đây, không cần lướt tin nhắn
trong Telegram để tìm.

1. **Đồng bộ ngay** — kéo về các đơn mới khách vừa đặt (tự làm khi mở tab
   này lần đầu cũng được, nhưng bấm nút để chắc chắn có đơn mới nhất). Lần
   đầu dùng, cần bấm **Cài đặt đồng bộ…** nhập Worker URL + Mã đồng bộ 1
   lần duy nhất (xem `bot/README.md` để lấy 2 giá trị này — **máy này đã
   điền sẵn rồi**, chỉ cần làm lại nếu dùng app trên 1 máy khác).
2. **Cần nhập hàng gì?** — xem tổng số lượng từng mặt hàng ở các đơn
   **CHƯA chốt vào đợt nào**. Nếu bạn không dùng "Chốt đợt hàng mới" (xem
   bên dưới), đây chính là toàn bộ đơn đang chờ xử lý — màn hình này
   dùng để đặt hàng nhà cung cấp luôn được.
   - Bảng chia cột riêng: **STT · Mã hàng · Tên hàng · Số lượng nhập ·
     Đơn vị · Quy cách · Khách đặt** — người kiểm hàng dò từng dòng là đủ.
     "Số lượng nhập" của mặt hàng NCC **chỉ bán nguyên bao/thùng** (ô "Tên đơn
     vị đóng gói lớn" có ghi, hiện chỉ có gạo) được quy đổi và **làm tròn LÊN**
     (vd khách đặt 2 kg gạo Kuban → nhập "1 bao", quy cách "25 KG"). Mặt hàng
     NCC bán lẻ (ô đó để trống: mì, phở, bột canh, vừng, mộc nhĩ...) thì ghi
     đúng số khách đặt.
   - **📋 Copy để gửi NCC (mỗi món 1 dòng)** → dán (Ctrl+V) thẳng vào tin
     nhắn gửi nhà cung cấp. **📋 Copy dạng bảng (dán vào Excel)** → dán vào
     Excel/Google Sheets, mỗi thông tin tự vào 1 cột (để in ra cho người kiểm).
   - Tên bao/thùng ("thùng", "túi", "bao"...) lấy từ ô **"Tên đơn vị đóng
     gói lớn"** trong dialog sửa mặt hàng (tab Danh mục hàng, cạnh "Số
     lượng sỉ"). **Để trống = NCC bán lẻ, không làm tròn**; "Số lượng sỉ" khi
     đó chỉ dùng để tính giá sỉ cho khách (vd mì 30 gói). **"Số lượng sỉ" = 1**
     = mặt hàng chỉ bán nguyên kiện (vd gạo St25 bán theo bao 5 kg): web hiện
     luôn giá sỉ làm giá bán.
   - Nếu CÓ dùng "Chốt đợt hàng mới", màn hình này chỉ là đơn chưa chốt
     (xem trước có gì đang tới). **Duyệt đợt hàng gần nhất…** (xem bên
     dưới) chỉ để loại mặt hàng hết hàng và báo khách — không còn nút Copy
     gửi NCC ở đó.
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
10. **📢 Đăng thông báo "đơn đã về" lên kênh** (trong cửa sổ "Duyệt đợt hàng"):
    app soạn sẵn bài theo mẫu quen thuộc ("Đơn đầu tháng … đã về!!! Ai có nhu cầu
    lấy liên hệ Hùng, Giang để nhận tại 705, hạn đến … Trân trọng.") — tên đợt
    và hạn nhận điền sẵn theo ngày hôm nay (hạn = 2 ngày sau), bạn sửa tự do
    trong khung soạn rồi bấm "Đăng lên kênh". Dòng đầu in đậm. Có hỏi xác nhận,
    đăng xong KHÔNG thu hồi được từ app. Cần deploy lại bot một lần
    (`npx wrangler deploy`) để có đường đăng bài chữ.
11. **Nhắc khách chưa nhận hàng — bot tự làm, bạn không cần mở app:**
    - Ngay khi bấm gửi "hàng đã về", bot nhắn riêng cho **bạn** 1 tin liệt
      kê từng khách kèm nút **"✅ Đã lấy: tên khách"**.
    - Khách nào tới lấy hàng, bạn bấm nút của khách đó **ngay trên điện
      thoại**. Khách nào **chưa được bấm** sau **24 giờ**, bot tự nhắn nhắc
      khách (chỉ trong giờ 9h–20h giờ Saint Petersburg, mỗi khách 1 lần):
      sang ngày mai (2 ngày kể từ lúc hàng về) chưa tới thì shop giao tận nơi và tính phí
      dịch vụ **100 ₽** (phí chung, không chia mức). Tin "hàng đã về" của từng khách cũng
      ghi sẵn câu này.
    - ⚠ Quên bấm "✅ Đã lấy" thì khách đã lấy hàng vẫn bị nhắc nhầm — nhớ bấm.
    - Việc **gửi tin "hàng đã về"** vẫn phải làm 1 lần trong app (cần nối
      hóa đơn NCC và chỉnh thiếu/thừa trước), chỉ phần nhắc 24 giờ là tự động.
    - **Nút "⏰ Nhắc khách chưa nhận hàng…"** (tab Đơn hàng online) để bạn
      tự bấm khi khách đã quá lâu chưa tới (sau lần bot tự nhắc). App liệt kê
      khách chưa có hóa đơn, hỏi xác nhận rồi gửi; bấm lại được, cách nhau
      ít nhất 24 giờ.

### Cài đặt

Nơi để 3 việc **không phải thao tác hằng ngày** — tách riêng khỏi các tab
khác để không bao giờ bị bấm nhầm trong lúc làm việc bình thường.

**Khôi phục từ bản sao lưu:**

- Dùng khi vừa thao tác nhầm (xóa sai hóa đơn, hủy sai đơn hàng online,
  sửa sai số...) và muốn quay lại trạng thái cũ. Chọn 1 bản trong danh
  sách (lấy từ các bản tự sao lưu mỗi lần mở app, xem [mục 3](#3-sao-lưu-dữ-liệu--đọc-trước-khi-làm-gì-khác)),
  bấm **Khôi phục…**.
- **Mất TOÀN BỘ thay đổi làm SAU thời điểm bản đó** (hóa đơn, thanh toán,
  đơn hàng online mới...), không riêng đúng 1 thao tác nhầm — nên chọn
  bản gần lúc xảy ra lỗi nhất có thể, không chọn đại bản cũ nhất cho an
  toàn. Dữ liệu hiện tại (trước khi khôi phục) cũng được tự sao lưu lại
  trước, để còn đường quay lại nếu lỡ chọn nhầm bản.
- App tự đóng sau khi khôi phục xong — mở lại để thấy dữ liệu đã khôi
  phục.

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
- **Liên hệ khách không có số điện thoại / @username:** tin báo đơn ghi đủ
  họ tên, bấm vào tên là mở hồ sơ khách. Chắc chắn nhất: trong chat với bot,
  **bấm giữ (hoặc chuột phải) tin báo đơn → Trả lời (Reply)** → gõ tin → bot
  gửi đúng cho khách đó và báo lại "✅ Đã gửi cho …". Khách nhắn lại (hay hỏi
  hàng bất cứ lúc nào) thì bot chuyển về thành tin "💬 Tin nhắn từ …" — lại
  bấm Trả lời vào tin đó để nhắn tiếp. Trả lời được tin trong 30 ngày.
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

## 7. Đọc hóa đơn nhà cung cấp bằng AI (tùy chọn)

Nút **"Đọc bảng hàng (AI)…"** ở tab **Hóa đơn nhà cung cấp** dùng 1 model
AI chạy ngay trên máy (qua phần mềm **Ollama**, miễn phí, không gửi ảnh
đi đâu cả) để đọc cả bảng mặt hàng trong ảnh. Cần cài 1 lần:

1. Tải Ollama tại: <https://ollama.com> (bản Windows), cài như phần mềm
   bình thường.
2. Mở Ollama (chạy nền, có icon ở khay hệ thống).
3. Mở terminal/PowerShell, chạy: `ollama pull qwen2.5vl:7b` (tải khoảng
   6GB, chỉ cần 1 lần).
4. Mở lại app — nút "Đọc bảng hàng (AI)" sẽ dùng được ngay.

**Nếu chưa cài Ollama, app vẫn chạy bình thường** — chỉ riêng nút này báo
lỗi rõ ràng bằng tiếng Việt, gõ tay vào bảng hóa đơn NCC vẫn dùng được
100%. Model này chạy chậm (15-30 giây/ảnh, hóa đơn dài có thể 1-3 phút) và **không phải lúc nào cũng
đọc đúng 100%** — luôn đối chiếu kết quả với ảnh thật và tổng tiền in
trên hóa đơn trước khi gõ vào bảng, đừng tin tuyệt đối.

### "Nhập vào đơn" — AI tự điền bảng (thay vì gõ tay từng dòng)

Sau khi bấm "Đọc bảng hàng (AI)…", nếu đọc thành công sẽ hiện thêm nút
**"Nhập vào đơn →"** — bấm vào, AI tự thêm các dòng vừa đọc được thành
**dòng nháp** trong bảng bên phải (tên, số lượng, đơn vị, đơn giá — kèm
cả tên tiếng Nga ở cột cuối để tham khảo). Những dòng này **chưa khớp mã
hàng** (trừ khi đúng tên đã từng khớp trước đó) và **chưa áp dụng gì vào
danh mục** — vẫn phải tự đối chiếu với ảnh thật, sửa lại chỗ sai, bấm
"Gợi ý mã hàng" để khớp từng dòng, rồi mới "Áp dụng giá mới vào danh
mục", y như khi gõ tay. Đổi ảnh hoặc xoay ảnh sẽ xóa các dòng AI vừa đọc
(tránh nhập nhầm dữ liệu của ảnh cũ).

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
dùng "Đọc bảng hàng (AI)" trên Mac: cài Ollama (<https://ollama.com>,
bản Mac) rồi `ollama pull qwen2.5vl:7b` — xem mục 7.

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

### Lấy lại code từ GitHub (nếu máy mới chưa có)

Repo riêng tư: `github.com/Friendzoner49/705bot` — cần đăng nhập GitHub
đúng tài khoản được cấp quyền:

```
git clone https://github.com/Friendzoner49/705bot.git
cd 705bot
uv sync
```

(Không có mạng hoặc không muốn dùng GitHub: dùng file `K:\705bot.bundle`
— xem `CLAUDE.md` mục 4 để biết cách `git clone` từ file này.)

## 9. Sự cố thường gặp

| Gặp phải | Cách xử lý |
|---|---|
| Số liệu trông sai lạ, lỡ thao tác nhầm (xóa/hủy/sửa sai) | Mở app, vào tab **Cài đặt → Khôi phục từ bản sao lưu**, chọn bản gần lúc xảy ra lỗi nhất (xem [mục 4](#4-hướng-dẫn-từng-tab-trong-app)) |
| Mở app báo lỗi, không mở được | App không mở được thì không bấm nút trong app được — đóng app (nếu đang treo), vào thẳng `%LOCALAPPDATA%\ShopApp\backups`, copy đè bản mới nhất vào `K:\705bot\data\shop.sqlite` (xem [mục 3](#3-sao-lưu-dữ-liệu--đọc-trước-khi-làm-gì-khác)) |
| Nút "Đọc bảng hàng (AI)…" báo lỗi | Chưa cài Ollama, chưa mở Ollama (chạy nền), hoặc chưa `ollama pull qwen2.5vl:7b` — xem [mục 7](#7-đọc-hóa-đơn-nhà-cung-cấp-bằng-ai-tùy-chọn). Mọi việc khác trong app vẫn dùng bình thường |
| "Cập nhật website giá" báo lỗi | Kiểm tra máy có đang nối mạng không; thử lại sau vài phút. Dữ liệu trong app không bị ảnh hưởng dù publish lỗi |
| "Đồng bộ ngay" (tab Đơn hàng online) báo lỗi | Kiểm tra mạng; nếu đang ở Nga có thể cần bật VPN. Đơn của khách không bị mất — bot vẫn giữ, đồng bộ lại sau vẫn lấy được |
| Gửi ảnh `/hangve` trong group nhưng app "Đồng bộ từ Telegram" không thấy gì mới | Kiểm tra theo đúng thứ tự: (1) đã tắt "Group Privacy" cho bot chưa (@BotFather → Bot Settings — cài đặt CHUNG của cả bot, không phải riêng 1 group); (2) đã **xóa rồi thêm lại bot vào group** sau khi tắt privacy chưa (Telegram chỉ áp dụng cho lần thêm TIẾP THEO, không hồi tố); (3) caption có bắt đầu đúng bằng `/hangve` không; (4) file gửi là Ảnh (Photo) hoặc File định dạng JPG/PNG — file HEIC (hay gặp khi gửi "Send as File" từ iPhone) bị từ chối, bot sẽ báo "Gửi dạng Ảnh"; (5) gửi đúng group đã cài `SUPPLIER_GROUP_CHAT_ID` chưa — group bị Telegram tự nâng cấp lên "supergroup" sẽ đổi ID, cần `/myid` lại. Xem `bot/README.md` mục 13 |
| Bấm "📢 Đăng lên kênh" báo lỗi | Kiểm tra: (1) đã cài `CHANNEL_CHAT_ID` chưa (`bot/README.md` mục 14); (2) bot còn quyền "Post Messages" trong kênh không (xem lại Administrators của kênh); (3) mặt hàng đã có ảnh chưa — chưa có ảnh thì không đăng được |
| Thấy 2 đơn giống hệt nhau trong "Đơn hàng online" | Hiếm khi xảy ra nếu lần gửi trước bị lỗi rồi khách gửi lại — bấm "Hủy đơn" cho bản thừa |
| Lỡ bấm "Khôi phục cài đặt gốc" hoặc "Nhập dữ liệu từ file" nhầm | App đã tự đóng/tự tạo 1 bản sao lưu ngay TRƯỚC khi hành động đó chạy — mở lại app, vào tab **Cài đặt → Khôi phục từ bản sao lưu**, chọn đúng bản đó |
| Bản Mac bị macOS chặn không mở được | Chạy `xattr -dr com.apple.quarantine /Applications/BachHoa705.app` trong Terminal — xem [mục 8](#8-cài-đặt-trên-máy-mới--cài-lại-từ-đầu) |
| Quên cách dùng 1 tính năng nào đó | Xem lại [mục 4](#4-hướng-dẫn-từng-tab-trong-app) ở trên, đúng tên nút đang thấy trong app |
| Cần biết thêm về cách bot hoạt động, cài đặt lại bot | Xem `bot/README.md` |
