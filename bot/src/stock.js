// Limited portions of a dish. The published catalog says how many were left
// when the app published ("remaining") and up to which moment orders are
// already counted ("stock_after", ms). Only portions ordered after that are
// subtracted here; the app stays the owner of the real count.
//
// They are kept in ONE KV key, so neither checkout nor the public /stock page
// needs a KV list() (free plan: ~1000 a day, shared with the app's sync).
const RECENT_KEY = "stock:recent";
const KEEP_MS = 14 * 24 * 60 * 60 * 1000;

const isLimited = (item) => Number.isFinite(item.remaining) && Number.isFinite(item.stock_after);

async function readRecent(env) {
  const raw = await env.ORDER_KV.get(RECENT_KEY);
  return raw ? JSON.parse(raw) : [];
}

// Called once per accepted order, for its limited dishes only.
export async function recordTaken(env, lines, now = Date.now()) {
  const taken = lines.filter((l) => isLimited(l.item)).map((l) => ({ ts: now, code: l.code, qty: l.qty }));
  if (taken.length === 0) return;
  const kept = (await readRecent(env)).filter((e) => e.ts > now - KEEP_MS);
  await env.ORDER_KV.put(RECENT_KEY, JSON.stringify([...kept, ...taken]));
}

// -> { CODE: portions left } for the limited items only.
export async function liveRemaining(env, items) {
  const limited = items.filter(isLimited);
  if (limited.length === 0) return {};
  const recent = await readRecent(env);
  const left = {};
  for (const item of limited) {
    const taken = recent
      .filter((e) => e.code === item.code && e.ts > item.stock_after)
      .reduce((sum, e) => sum + e.qty, 0);
    left[item.code] = Math.max(0, item.remaining - taken);
  }
  return left;
}

// The lines of an order that ask for more than is left. If the count can't be
// read, let the order through: the owner still confirms every order by hand.
export async function shortLines(env, lines) {
  let left;
  try {
    left = await liveRemaining(env, lines.map((l) => l.item));
  } catch (err) {
    console.error("stock check failed:", err);
    return [];
  }
  return lines.filter((l) => l.code in left && l.qty > left[l.code]).map((l) => ({ ...l, left: left[l.code] }));
}

export function shortText(short) {
  const rows = short.map(({ item, left }) =>
    left > 0 ? `• ${item.name}: chỉ còn ${left} suất` : `• ${item.name}: đã hết suất`,
  );
  return [
    "Rất tiếc, đơn chưa được gửi vì không đủ số suất:",
    ...rows,
    "",
    'Bấm "🛒 Đặt hàng" để chọn lại số lượng.',
  ].join("\n");
}

// Dishes whose order deadline (published with its UTC offset) has passed, e.g.
// a Mini App opened before the deadline and sent after it.
export function closedLines(lines, now = Date.now()) {
  return lines.filter((l) => l.item.deadline && now >= Date.parse(l.item.deadline));
}

export function closedText(closed) {
  const rows = closed.map(({ item }) => {
    const [, month, day] = item.deadline.slice(0, 10).split("-");
    return `• ${item.name}: đã hết hạn đặt lúc ${item.deadline.slice(11, 16)} ngày ${day}/${month}`;
  });
  return ["Rất tiếc, đơn chưa được gửi vì đã quá hạn đặt:", ...rows, "", 'Bấm "🛒 Đặt hàng" để chọn lại.'].join("\n");
}
