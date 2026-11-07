// Remembers a customer's checkout answer (a phone number, or an
// explicit "skip") INDEFINITELY (no TTL) once they've answered it the
// first time -- so a returning customer using the Mini App's "Xác nhận
// gửi đơn" button never has to answer it again; see CLAUDE.md section 7
// (lần 12), which is what actually gets the "accept once, then
// automatic" flow the shop owner asked for. Keyed by Telegram chat id,
// same ORDER_KV namespace as orderStore.js (different prefix).
export async function getRememberedCustomer(env, chatId) {
  const raw = await env.ORDER_KV.get(`customer:${chatId}`);
  return raw ? JSON.parse(raw) : null;
}

export async function rememberCustomer(env, chatId, data) {
  await env.ORDER_KV.put(`customer:${chatId}`, JSON.stringify(data));
}

// Self-service escape hatch for /doisdt -- without this, a customer who
// wants to switch from "skip" to sharing a real phone number (or just
// update it) would need someone to clear KV by hand.
export async function forgetCustomer(env, chatId) {
  await env.ORDER_KV.delete(`customer:${chatId}`);
}
