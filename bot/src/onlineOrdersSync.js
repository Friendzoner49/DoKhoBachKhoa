// A durable, independent record of every checkout -- written whether or
// not the admin's Telegram actually received the order (that's the
// whole point of having a second channel: the admin-chat message can
// fail -- see handlers.js finishCheckout -- or just get buried in a
// long chat history). The desktop app pulls from here via GET
// /sync/orders (see index.js) instead of the admin having to read
// every message by eye. See CLAUDE.md section 7 (lần 13).
//
// Keys are time-sortable so a plain string list() + sort gives
// chronological order without needing an atomic counter (KV doesn't
// have one). The random suffix is just cheap insurance against two
// orders landing in the same millisecond.
const PREFIX = "sync:";
const TTL_SECONDS = 60 * 60 * 24 * 90; // 90 days -- plenty of time for the app to pick it up

function makeSyncKey(chatId) {
  const ts = String(Date.now()).padStart(13, "0");
  const rand = Math.random().toString(36).slice(2, 6);
  return `${PREFIX}${ts}-${chatId}-${rand}`;
}

export async function recordSyncOrder(env, record) {
  const key = makeSyncKey(record.telegram_chat_id);
  await env.ORDER_KV.put(key, JSON.stringify(record), { expirationTtl: TTL_SECONDS });
  return key;
}

// `since`, when given, is a previously-returned key -- only strictly
// greater (lexicographically, which matches chronologically given the
// key format above) keys are returned, so the app can hand back the
// last key it saw instead of re-downloading everything every time.
export async function listSyncOrders(env, since) {
  const names = [];
  let cursor;
  for (;;) {
    const page = await env.ORDER_KV.list({ prefix: PREFIX, cursor });
    for (const k of page.keys) {
      if (!since || k.name > since) names.push(k.name);
    }
    if (page.list_complete || !page.cursor) break;
    cursor = page.cursor;
  }
  names.sort();

  const orders = [];
  for (const key of names) {
    const raw = await env.ORDER_KV.get(key);
    if (raw) orders.push({ key, ...JSON.parse(raw) });
  }
  return orders;
}
