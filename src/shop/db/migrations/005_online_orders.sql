-- Orders placed by customers through the Telegram bot, pulled in from
-- the bot's Cloudflare Worker (GET /sync/orders) -- see
-- shop.core.online_orders and CLAUDE.md section 6/7 (lần 13). This is
-- a read-and-act mirror of what the bot already sent as a Telegram
-- message; the bot's copy is display-only, this table is what the app
-- actually works from so "I don't see pending orders anywhere in the
-- app" stops being true.

CREATE TABLE online_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE, -- the bot's sync: KV key -- de-dup on re-sync
    telegram_chat_id TEXT NOT NULL,
    customer_label TEXT NOT NULL, -- name/@handle as Telegram gave it, for display only
    customer_phone TEXT,
    total_estimated INTEGER NOT NULL DEFAULT 0, -- the bot's estimate; convert_to_invoice recomputes from current prices
    status TEXT NOT NULL DEFAULT 'cho_xu_ly' CHECK (status IN ('cho_xu_ly', 'da_tao_hoa_don', 'da_huy')),
    linked_invoice_id INTEGER REFERENCES invoices(id),
    placed_at TEXT NOT NULL, -- when the customer checked out, from the bot's record
    synced_at TEXT NOT NULL -- when the app pulled this in
);

CREATE TABLE online_order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    online_order_id INTEGER NOT NULL REFERENCES online_orders(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    qty REAL NOT NULL,
    name_at_order TEXT NOT NULL, -- snapshot from the bot at order time, for display even if the product is renamed/deleted later
    price_at_order INTEGER NOT NULL
);

CREATE INDEX idx_online_order_lines_order ON online_order_lines(online_order_id);
CREATE INDEX idx_online_orders_status ON online_orders(status);

-- Remembers which app customer a given Telegram chat id maps to, so
-- converting a later order from the same chat pre-selects them instead
-- of asking every time. Set the first time an order from that chat is
-- converted to an invoice; never written automatically otherwise.
CREATE TABLE telegram_customer_links (
    telegram_chat_id TEXT PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id)
);
