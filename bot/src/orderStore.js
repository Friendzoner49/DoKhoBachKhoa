// KV-backed storage for the ONE pending order a chat is in the middle
// of checking out -- not an accumulating shopping cart. A website
// message always REPLACES whatever was here before (see handlers.js):
// each website message is a complete order, not an addition to one, so
// re-sending it (or editing the website cart and sending again) must
// never double quantities.
const TTL_SECONDS = 60 * 60 * 24; // abandoned mid-checkout -- a day is plenty

export async function getPendingOrder(env, chatId) {
  const raw = await env.ORDER_KV.get(`order:${chatId}`);
  return raw ? JSON.parse(raw) : {};
}

export async function setPendingOrder(env, chatId, order) {
  await env.ORDER_KV.put(`order:${chatId}`, JSON.stringify(order), { expirationTtl: TTL_SECONDS });
}

export async function clearPendingOrder(env, chatId) {
  await env.ORDER_KV.delete(`order:${chatId}`);
}
