-- Seasonal/limited-time products (lần 21): a product can carry a sale
-- window ("mở bán giới hạn 3-5 ngày"), shown as a countdown badge on
-- the website and auto-hidden once past (website computes this from
-- today's date client-side -- see index.html -- so it stays hidden
-- exactly on time without needing the owner to republish or flip a
-- flag). channel_announced_at is purely informational (lets the app
-- show "Đã đăng lúc ..." next to the "Đăng lên kênh" button) -- it
-- never blocks a re-post.
ALTER TABLE products ADD COLUMN sale_until TEXT;
ALTER TABLE products ADD COLUMN channel_announced_at TEXT;
