// Telegram only lets a bot delete a message (its own or the admin's)
// within 48 hours of it being sent -- no exception, no command can get
// around that (see bot/README.md's /xoatinnhan section). This just
// tracks message ids in the admin's chat so /xoatinnhan can batch-
// delete whatever is still inside that window; anything older needs
// Telegram's own "Xóa lịch sử trò chuyện" instead.
const KEY = "admin_message_log";
const MAX_AGE_MS = 48 * 60 * 60 * 1000;
const MAX_ENTRIES = 2000; // sanity cap; pruning should normally keep this far lower

export async function recordAdminMessage(env, messageId) {
  if (!messageId) return;
  const now = Date.now();
  const raw = await env.ORDER_KV.get(KEY);
  let entries = raw ? JSON.parse(raw) : [];
  entries = entries.filter((e) => now - e.ts < MAX_AGE_MS);
  entries.push({ id: messageId, ts: now });
  if (entries.length > MAX_ENTRIES) {
    entries = entries.slice(entries.length - MAX_ENTRIES);
  }
  await env.ORDER_KV.put(KEY, JSON.stringify(entries));
}

// Returns the still-maybe-deletable ids and resets the log. Telegram's
// deleteMessages silently skips any id it can't delete (already gone,
// or past the 48h window) instead of erroring, so no need to be exact
// about freshness here -- the caller just needs "not wildly stale".
export async function takeDeletableAdminMessages(env) {
  const raw = await env.ORDER_KV.get(KEY);
  const entries = raw ? JSON.parse(raw) : [];
  await env.ORDER_KV.delete(KEY);
  const now = Date.now();
  return entries.filter((e) => now - e.ts < MAX_AGE_MS).map((e) => e.id);
}
