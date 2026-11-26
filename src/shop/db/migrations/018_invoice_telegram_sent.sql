-- Set only after the Worker confirms the invoice summary reached the customer on Telegram.
ALTER TABLE invoices ADD COLUMN telegram_sent_at TEXT;
