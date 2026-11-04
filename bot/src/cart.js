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

// Mirrors shop.core.pricing.BULK_DISCOUNT_FACTOR (26/10/2026) -- the
// invoice itself applies this same 2% once qty reaches an item's
// bulk_qty (shop.core.invoices._resync_bulk_discount), so the bot's
// quoted total must match what the customer actually gets billed.
const BULK_DISCOUNT_FACTOR = 0.98;

function bulkPrice(price, bulkQty) {
  return Math.round(price * bulkQty * BULK_DISCOUNT_FACTOR);
}

export function lineTotal(item, qty) {
  if (!item.bulk_qty || qty < item.bulk_qty) {
    return Math.round(item.price * qty);
  }
  // Mirrors shop.core.pricing.bulk_discount (27/10/2026, lần 29): the
  // sỉ rate only applies to each COMPLETE bulk_qty tier ("1 thùng/bao");
  // the leftover is billed at the plain per-unit rate, not a blanket
  // discount on the whole qty just because it crossed the threshold
  // once. The small epsilon guards against float division landing a
  // hair under a whole number of tiers.
  const fullTiers = Math.floor(qty / item.bulk_qty + 1e-9);
  const remainder = qty - fullTiers * item.bulk_qty;
  return fullTiers * bulkPrice(item.price, item.bulk_qty) + Math.round(item.price * remainder);
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
    total += lineTotal(item, qty);
  }
  out.push("—");
  out.push(`Tổng ước tính: ${numberFormat.format(total)} ₽`);
  if (customer) {
    out.push(`Khách: ${customer.label}`);
    if (customer.phone) out.push(`SĐT: ${customer.phone}`);
  }
  return { text: out.join("\n"), total };
}
