// Pure order-text math -- no KV, no Telegram, no network. Kept
// separate from orderStore.js (the KV-backed wrapper) so this logic is
// unit-testable with plain `node --test`, matching the shop.core
// pattern of keeping business logic free of I/O.
import { numberFormat } from "./format.js";

// Drops codes no longer in the published catalog (e.g. discontinued
// between the website export and the customer tapping "send").
export function orderLines(order, items) {
  return Object.entries(order)
    .map(([code, qty]) => ({ code, qty, item: items.find((i) => i.code === code) }))
    .filter((line) => line.item);
}

// Same header/line/footer shape as the website's buildOrderText(), so
// a future "paste order from Telegram" importer in the app can parse
// either source with the same `^(\S+)\s*x\s*(\d+)` regex (see CLAUDE.md
// section 6). `customer` is appended after the total, never inside the
// item lines, so it can't be mistaken for one.
//
// `customer` is `{ label, phone }` (phone optional) -- never a single
// pre-joined string, so handlers.js can't accidentally interpolate a
// product name into it.
export function buildOrderText(lines, customer) {
  const out = ["Đơn đặt hàng từ Telegram bot:"];
  let total = 0;
  for (const { item, qty } of lines) {
    out.push(`${item.code} x${qty} — ${item.name}`);
    total += item.price * qty;
  }
  out.push("—");
  out.push(`Tổng ước tính: ${numberFormat.format(total)} ₽`);
  if (customer) {
    out.push(`Khách: ${customer.label}`);
    if (customer.phone) out.push(`SĐT: ${customer.phone}`);
  }
  return { text: out.join("\n"), total };
}
