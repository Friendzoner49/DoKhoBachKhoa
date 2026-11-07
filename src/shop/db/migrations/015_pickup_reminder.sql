-- "Nhắc khách chưa nhận hàng": set once the Worker confirms the reminder DM
-- went out, so a retry never double-messages (same idea as arrival_notified_at, 010).
ALTER TABLE online_orders ADD COLUMN pickup_reminded_at TEXT;
