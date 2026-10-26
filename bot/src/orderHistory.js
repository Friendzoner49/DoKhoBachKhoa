// Remembers each customer's own order history (their last order's lines,
// plus how many separate past orders contained each code) so the "🛒
// Đặt hàng" keyboard button can hand the website a personalized reorder
// shortcut + "hay mua" badges -- see CLAUDE.md section 6/7 (lần 14). Keyed by Telegram
// chat id, same ORDER_KV namespace as customerStore.js, no TTL. This is
// a UX hint only, never the record of truth -- the desktop app's
// online_orders table (via onlineOrdersSync.js) is what the shop owner
// actually acts on.
const TOP_CODES_LIMIT = 8;

export async function getOrderHistory(env, chatId) {
  const raw = await env.ORDER_KV.get(`history:${chatId}`);
  return raw ? JSON.parse(raw) : null;
}

// lines: [{code, qty}] of the order that was just placed. Returns the
// updated history object -- callers that need it right away (see
// orderKeyboard() in handlers.js) must use THIS return value instead of
// reading it back from KV in the same request, since Workers KV only
// guarantees eventual (not read-your-own-write) consistency.
export async function recordOrderHistory(env, chatId, lines) {
  const existing = await getOrderHistory(env, chatId);
  const frequency = existing?.frequency || {};
  // +1 per ORDER that contained this code, not per quantity -- "hay
  // mua" means "ordered repeatedly", not "ordered a lot of in one go"
  // (a single 10-pack order shouldn't outrank 5 separate 1-pack ones).
  // Dedup codes within this one order first so a duplicate line never
  // counts as two separate orders.
  for (const code of new Set(lines.map((l) => l.code))) {
    frequency[code] = (frequency[code] || 0) + 1;
  }
  const lastOrder = lines.map(({ code, qty }) => ({ code, qty }));
  const history = { lastOrder, frequency };
  await env.ORDER_KV.put(`history:${chatId}`, JSON.stringify(history));
  return history;
}

// Only codes ordered in at least 2 separate past orders count as
// "hay mua" -- after a customer's very first order, every item in it
// would otherwise immediately get the badge, which is really just
// restating the last order, not a genuine repeat-purchase signal.
const MIN_ORDERS_FOR_TOP = 2;

export function topCodes(history, limit = TOP_CODES_LIMIT) {
  if (!history || !history.frequency) return [];
  return Object.entries(history.frequency)
    .filter(([, orderCount]) => orderCount >= MIN_ORDERS_FOR_TOP)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([code]) => code);
}

// Capped well below any practical URL-length limit -- this is a UX
// shortcut embedded in a keyboard button URL, not a data record, so
// silently truncating the rare very-large-order case is fine (the
// customer can always just re-add items by hand).
const MAX_LAST_ORDER_ITEMS = 40;

// Builds the personalized URL embedded in the "🛒 Đặt hàng" keyboard
// button (see orderKeyboard() in handlers.js) -- `?last=CODE:QTY,...`
// for the "Đặt lại đơn trước" shortcut and `?top=CODE,...` for the
// "hay mua" badges, both read client-side by index.html. No new
// Worker endpoint involved: this data already lives in KV from this
// same chat's own past checkouts, and it's handed to the customer's
// OWN browser via a URL the bot itself generates per-chat.
export function buildPersonalizedSiteUrl(baseUrl, history) {
  if (!history) return baseUrl;
  const params = new URLSearchParams();
  if (history.lastOrder && history.lastOrder.length > 0) {
    const encoded = history.lastOrder
      .slice(0, MAX_LAST_ORDER_ITEMS)
      .map(({ code, qty }) => `${code}:${qty}`)
      .join(",");
    params.set("last", encoded);
  }
  const top = topCodes(history);
  if (top.length > 0) params.set("top", top.join(","));
  const qs = params.toString();
  if (!qs) return baseUrl;
  return baseUrl + (baseUrl.includes("?") ? "&" : "?") + qs;
}
