// Automatic "chưa tới nhận hàng" reminder, 24h after the app sent the
// "hàng đã về" DM -- the owner can't open the desktop app every day, so
// the Worker does this on its own (Cron Trigger, see wrangler.toml).
//
// How the Worker knows a customer already collected: it doesn't guess.
// For every arrival DM the Worker relays, it also DMs the ADMIN one
// message with a "✅ Đã lấy: <tên>" button per customer; the owner taps
// it on the phone when the customer collects, which deletes that
// customer's pending reminder. Only ADMIN_CHAT_ID can tap it.
//
// KV key `pickup:<online_order_id>` -> {chat_id, label, notified_at,
// reminded_at?}. TTL 7 days: an entry nobody ever tapped just expires.
const PREFIX = "pickup:";
const TTL_SECONDS = 60 * 60 * 24 * 7;
const REMIND_AFTER_MS = 24 * 60 * 60 * 1000;
const MAX_SENDS_PER_RUN = 40; // free tier: 50 subrequests per invocation
export const PICKUP_CALLBACK_PREFIX = "pk:";

export const REMINDER_TEXT =
  "⏰ Hàng bạn đặt đã về được 1 ngày rồi, bạn nhớ tới nhận nhé.\n" +
  "Nếu sang ngày mai (2 ngày kể từ lúc hàng về) bạn vẫn chưa tới nhận, shop sẽ giao tận nơi (ship tận giường) và tính phí dịch vụ 100 ₽.";

// Called right after the arrival DMs went out. `sent` = the app's
// entries (only those with remind:true and an order_id) whose DM the
// Telegram call accepted. Returns nothing; failures here must never
// break the arrival response the app is waiting on.
export async function registerPickups(env, tg, sent, now = Date.now()) {
  const entries = sent.filter((m) => m.remind && Number.isInteger(m.order_id));
  if (entries.length === 0) return;
  for (const m of entries) {
    await env.ORDER_KV.put(
      `${PREFIX}${m.order_id}`,
      JSON.stringify({ chat_id: String(m.chat_id), label: m.label || "", notified_at: now }),
      { expirationTtl: TTL_SECONDS },
    );
  }
  if (!env.ADMIN_CHAT_ID) return;
  // ONE admin message with one button per customer (1 subrequest, not N).
  const keyboard = entries.map((m) => [
    { text: `✅ Đã lấy: ${String(m.label || m.order_id).slice(0, 30)}`, callback_data: `${PICKUP_CALLBACK_PREFIX}${m.order_id}` },
  ]);
  await tg.sendMessage(
    env.ADMIN_CHAT_ID,
    "📦 Đã báo hàng về. Khách nào tới lấy hàng thì bấm tên để bot KHÔNG nhắc sau 1 ngày " +
      "(bot tự nhắc khách chưa được bấm sau 24 giờ).",
    { reply_markup: { inline_keyboard: keyboard } },
  );
}

// Admin tapped "✅ Đã lấy". Returns true if a pending entry was removed.
export async function markPickedUp(env, orderId) {
  const key = `${PREFIX}${orderId}`;
  const had = await env.ORDER_KV.get(key);
  await env.ORDER_KV.delete(key);
  return had !== null;
}

// Cron entry point. `now` is injectable so tests can fix the clock.
export async function runPickupReminders(env, tg, now = Date.now()) {
  const names = [];
  let cursor;
  for (;;) {
    const page = await env.ORDER_KV.list({ prefix: PREFIX, cursor });
    for (const k of page.keys) names.push(k.name);
    if (page.list_complete || !page.cursor) break;
    cursor = page.cursor;
  }
  names.sort();

  let sends = 0;
  for (const key of names) {
    if (sends >= MAX_SENDS_PER_RUN) break; // the rest go on the next run
    const raw = await env.ORDER_KV.get(key);
    if (!raw) continue;
    const entry = JSON.parse(raw);
    if (entry.reminded_at || now - entry.notified_at < REMIND_AFTER_MS) continue;
    sends += 1;
    let error;
    try {
      await tg.sendMessage(entry.chat_id, REMINDER_TEXT);
    } catch (err) {
      error = String(err.message || err); // e.g. the customer blocked the bot
    }
    // Marked either way: a blocked chat must not be retried every hour.
    await env.ORDER_KV.put(key, JSON.stringify({ ...entry, reminded_at: now, ...(error ? { error } : {}) }), {
      expirationTtl: TTL_SECONDS,
    });
  }
  return sends;
}
