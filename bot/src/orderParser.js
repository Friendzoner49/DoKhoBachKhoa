// The website's cart composes its order text as one `CODE xQTY — Name`
// line per item (see src/shop/site_template/index.html's
// buildOrderText() and CLAUDE.md section 6) -- the exact same shape
// the app's future "paste order" importer is meant to parse. That text
// arrives as the bot's first message verbatim when a customer taps the
// website's "send to bot" link, so the bot understands it directly by
// CODE (the header/footer lines, e.g. "Tổng ước tính: …", simply don't
// match this pattern and are ignored).
//
// This is the ONLY thing the bot parses -- it's a receive-and-forward
// channel, not a storefront (ordering happens on the website; see
// CLAUDE.md section 6 and section 7's decision log for why in-bot
// browsing/search/natural-language parsing were tried and then
// removed).
const CODE_QTY_RE = /^(\S+)\s*x\s*(\d+)/i;

export function parseCodeOrderLines(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .map((line) => {
      const m = line.match(CODE_QTY_RE);
      return m ? { code: m[1], qty: Math.max(1, parseInt(m[2], 10)) } : null;
    })
    .filter(Boolean);
}

// The website, when opened as a Telegram Mini App (launched from the
// bot's own "🛒 Đặt hàng" keyboard button), submits the cart via
// Telegram.WebApp.sendData() instead of the usual prefilled-text link
// -- see CLAUDE.md section 7 (lần 12). The payload is deliberately
// minimal ({code, qty} pairs only, no name/price: the Worker always
// re-looks-up current price/name from the catalog, never trusts
// anything the client sent). Malformed or absurd input (not from our
// own site, or a bug in it) degrades to "no lines recognized" rather
// than throwing, same as parseCodeOrderLines above.
const MAX_WEB_APP_LINES = 300;

export function parseWebAppOrderLines(raw) {
  let data;
  try {
    data = JSON.parse(raw);
  } catch (_err) {
    return [];
  }
  if (!data || !Array.isArray(data.lines)) return [];
  return data.lines
    .filter((l) => l && typeof l.code === "string" && l.code && Number.isFinite(l.qty))
    .map((l) => ({ code: l.code, qty: Math.max(1, Math.min(9999, Math.floor(l.qty))) }))
    .slice(0, MAX_WEB_APP_LINES);
}
