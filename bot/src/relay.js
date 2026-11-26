// Owner <-> customer messaging through the bot (21/11/2026): many customers
// have no @username and skip the phone question, so an order alone gave
// the owner no way to reach them. Every message the bot sends the owner on
// a customer's behalf (an order, or the customer's own free text) is
// remembered here as admin message id -> customer chat id; the owner taps
// "Trả lời" (Reply) on it and the bot relays the reply to THAT customer.
//
// Data isolation (CLAUDE.md: one customer's data never reaches another):
// Telegram message ids are per chat, so keys are scoped to ADMIN_CHAT_ID
// and handlers.js only ever looks one up for a reply sent IN the admin
// chat -- a customer replying in their own chat never touches this map.
const RELAY_TTL_SECONDS = 30 * 24 * 60 * 60;

function relayKey(env, adminMessageId) {
  return `relay:${env.ADMIN_CHAT_ID}:${adminMessageId}`;
}

export async function rememberRelay(env, adminMessageId, customer) {
  if (!env.ADMIN_CHAT_ID || adminMessageId == null) return;
  await env.ORDER_KV.put(relayKey(env, adminMessageId), JSON.stringify(customer), {
    expirationTtl: RELAY_TTL_SECONDS,
  });
}

export async function lookupRelay(env, adminMessageId) {
  if (!env.ADMIN_CHAT_ID || adminMessageId == null) return null;
  const raw = await env.ORDER_KV.get(relayKey(env, adminMessageId));
  return raw ? JSON.parse(raw) : null;
}

// Full name as Telegram gives it (first + last), never empty.
export function customerName(from) {
  return [from?.first_name, from?.last_name].filter(Boolean).join(" ").trim() || "Khách";
}

// A tappable name (text_mention) for a customer with or without a
// @username: opens their profile in the owner's Telegram. `marker` is the
// text right before the name ("Khách: "); offsets are JS string indices,
// i.e. UTF-16 code units -- exactly what Telegram expects.
export function nameMention(text, marker, name, userId) {
  const at = text.indexOf(marker);
  if (at < 0 || userId == null) return [];
  const offset = at + marker.length;
  if (text.slice(offset, offset + name.length) !== name) return [];
  return [{ type: "text_mention", offset, length: name.length, user: { id: userId, is_bot: false, first_name: name } }];
}

export const REPLY_HINT = "↩️ Bấm Trả lời (Reply) vào tin này để nhắn cho khách.";
