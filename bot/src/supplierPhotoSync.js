// A durable record of supplier-invoice photos sent as "/hangve <ghi
// chú>" in the Telegram group (see handlers.js) -- same shape and same
// reasons as onlineOrdersSync.js: the desktop app pulls from here via
// GET /sync/photos (see index.js) instead of the photo only existing
// as a Telegram message the owner has to find and save by hand.
//
// Keys are time-sortable so a plain string list() + sort gives
// chronological order without needing an atomic counter (KV doesn't
// have one). Reuses the same ORDER_KV namespace as orders/history/etc
// (see CLAUDE.md section 7) -- distinguished only by the key prefix,
// same convention already used there.
const PREFIX = "photo:";
const TTL_SECONDS = 60 * 60 * 24 * 90; // 90 days -- plenty of time for the app to pick it up

// Built from the Telegram MESSAGE's own data (its `date`, in seconds,
// and the chosen file's `file_unique_id`) -- NOT Date.now()/Math.random()
// -- so that Telegram redelivering the same webhook update (it retries
// on timeout) reuses the exact same key and overwrites the same KV
// entry instead of minting a second one. Without this, a redelivery
// would create two separate draft supplier_invoices rows in the app
// for what is really one photo (source_key is UNIQUE there, but two
// DIFFERENT keys both look "new" to it).
function makePhotoKey(messageDateSec, fileUniqueId) {
  const ts = String(messageDateSec * 1000).padStart(13, "0");
  return `${PREFIX}${ts}-${fileUniqueId}`;
}

// `dataBase64` is the photo's own bytes, base64-encoded -- KV stores a
// string/bytes value directly (25MB limit per key, a phone photo is
// nowhere close), and returning it inline in the sync response is
// simpler than a second per-photo download round trip for the small
// volume this feature actually sees (a handful of deliveries a month).
export async function recordSupplierPhoto(env, { note, dataBase64, messageDateSec, fileUniqueId }) {
  const key = makePhotoKey(messageDateSec, fileUniqueId);
  await env.ORDER_KV.put(key, JSON.stringify({ note: note || "", data: dataBase64 }), { expirationTtl: TTL_SECONDS });
  return key;
}

// `since`, when given, is a previously-returned key -- only strictly
// greater (lexicographically, which matches chronologically given the
// key format above) keys are returned, mirroring listSyncOrders.
export async function listSupplierPhotos(env, since) {
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

  const photos = [];
  for (const key of names) {
    const raw = await env.ORDER_KV.get(key);
    if (raw) photos.push({ key, ...JSON.parse(raw) });
  }
  return photos;
}
