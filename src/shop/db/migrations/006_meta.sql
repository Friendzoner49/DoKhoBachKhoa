-- Small generic key/value store for app-level flags that aren't tied to
-- any one table. First (and currently only) use: online_orders'
-- "sync_floor" (shop.core.online_orders.set_sync_floor / shop.core.reset),
-- written after a factory reset so the next "Đồng bộ ngay" doesn't
-- immediately re-pull every pre-reset test order still sitting in the
-- bot's KV (90-day TTL).

CREATE TABLE shop_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
