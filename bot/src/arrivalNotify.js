// "Hàng đã về" DMs (request 25/10/2026, the other half of lần 18's
// "hàng về -> thu tiền" plan -- "📢 Đăng lên kênh" from lần 21 already
// covers the public channel side). The app has already built each
// customer's own message (shop.core.arrival_notify) and batches them
// into chunks of ~40 (Cloudflare Workers free tier: 50 subrequests per
// invocation, see CLAUDE.md lần 13) -- this just relays each one to
// Telegram and reports per-chat success/failure, so a blocked bot or a
// deleted chat for ONE customer never aborts the rest of the batch.
//
// Messages the app marks `remind: true` (with an `order_id`) also get an
// automatic "chưa tới nhận" reminder 24h later -- see pickupReminders.js.
import { registerPickups } from "./pickupReminders.js";
import { telegramApi } from "./telegram.js";

export async function sendArrivalMessages(env, messages) {
  const tg = telegramApi(env.BOT_TOKEN);
  const results = [];
  const sentOk = [];
  for (const m of messages) {
    try {
      await tg.sendMessage(m.chat_id, m.text);
      results.push({ chat_id: m.chat_id, ok: true });
      sentOk.push(m);
    } catch (err) {
      // e.g. "Forbidden: bot was blocked by the user" -- the owner
      // sees this chat_id in the app's "cần tự liên hệ" list instead
      // of the whole send silently failing.
      results.push({ chat_id: m.chat_id, ok: false, error: String(err.message || err) });
    }
  }
  try {
    await registerPickups(env, tg, sentOk);
  } catch (err) {
    // Never fail the arrival response the app is waiting on (it would
    // wrongly look like "no DM was sent"): the DMs already went out.
    console.error("registerPickups failed:", err);
  }
  return results;
}
