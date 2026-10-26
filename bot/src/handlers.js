import { telegramApi } from "./telegram.js";
import { fetchCatalog, findByCode } from "./catalog.js";
import { getPendingOrder, setPendingOrder, clearPendingOrder } from "./orderStore.js";
import { getRememberedCustomer, rememberCustomer, forgetCustomer } from "./customerStore.js";
import { getOrderHistory, recordOrderHistory, buildPersonalizedSiteUrl } from "./orderHistory.js";
import { recordAdminMessage, takeDeletableAdminMessages } from "./adminMessageLog.js";
import { recordSyncOrder } from "./onlineOrdersSync.js";
import { recordSupplierPhoto } from "./supplierPhotoSync.js";
import { orderLines, buildOrderText } from "./cart.js";
import { parseCodeOrderLines, parseWebAppOrderLines } from "./orderParser.js";

// This bot is a receive-and-forward channel -- ordering happens on the
// website (see CLAUDE.md section 6/7: an earlier version had in-bot
// category browsing, search and even a small natural-language parser,
// but the shop owner found tapping through buttons for several
// different items too slow, and asked for the bot to just catch the
// website's handoff and forward it). Since lần 12, "the website" can
// also run INSIDE Telegram as a Mini App (opened from the keyboard
// button below), which lets a customer submit an order with a single
// tap and no manual "type/find Send" step -- see orderKeyboard() and
// the web_app_data branch in handleMessage.
const SKIP_PHONE_TEXT = "Bỏ qua, chỉ dùng Telegram";

// Shown on /start and re-sent after every checkout, because a reply
// keyboard is replaced wholesale by whichever `reply_markup` a message
// carries -- the phone-prompt keyboard would otherwise permanently
// clobber this one after a customer's first order.
//
// The button's URL is personalized per chat (lần 14): if this customer
// has ordered before, their last order + most-ordered codes (from
// orderHistory.js, same ORDER_KV this bot already reads/writes) are
// appended as query params, which index.html reads to offer "Đặt lại
// đơn trước" and a "hay mua" badge. No new Worker endpoint -- this is
// just a URL this bot itself builds, same as always.
//
// `history`, if passed, is used AS-IS instead of re-reading KV -- same
// stale-read-after-write trap as lần 12's finishCheckout fix: a caller
// that just wrote history:<chatId> this same request (finishCheckout,
// right after a checkout) must hand that write's own return value here,
// not trust a fresh get() to see it on real (not mocked) KV.
async function orderKeyboard(env, chatId, history) {
  const resolvedHistory = history !== undefined ? history : chatId != null ? await getOrderHistory(env, chatId).catch(() => null) : null;
  return {
    keyboard: [[{ text: "🛒 Đặt hàng", web_app: { url: buildPersonalizedSiteUrl(env.SITE_BASE_URL, resolvedHistory) } }]],
    resize_keyboard: true,
  };
}

function welcomeText(env) {
  return [
    "Chào bạn 👋",
    "",
    'Bấm nút "🛒 Đặt hàng" bên dưới để xem bảng giá và đặt hàng ngay trong Telegram -- chọn hàng xong bấm "Xác nhận gửi đơn" là đơn tới thẳng người bán, không cần gõ gì thêm.',
    "",
    'Nếu bạn vừa bấm "Gửi đơn qua Telegram" từ website (không qua nút bên dưới): nội dung đơn đang nằm sẵn trong ô nhập tin nhắn -- chỉ cần bấm nút Gửi (➤) là xong.',
    "",
    `Muốn xem trên trình duyệt bình thường cũng được: ${env.SITE_BASE_URL}`,
    "",
    "Có câu hỏi khác? Gõ /contact.",
  ].join("\n");
}

async function sendWelcome(chatId, ctx) {
  await ctx.tg.sendMessage(chatId, welcomeText(ctx.env), { reply_markup: await orderKeyboard(ctx.env, chatId) });
}

function makeItemsGetter(env) {
  let cached = null;
  return async () => {
    if (!cached) cached = await fetchCatalog(env);
    return cached;
  };
}

// Every message the bot sends to the admin's own chat gets its id
// logged (see adminMessageLog.js), so /xoatinnhan has something to
// clean up later. Wrapping sendMessage here, once, covers every call
// site below without having to remember to log at each one.
function wrapAdminMessageTracking(tg, env) {
  if (!env.ADMIN_CHAT_ID) return tg;
  return {
    ...tg,
    sendMessage: async (chatId, text, extra) => {
      const result = await tg.sendMessage(chatId, text, extra);
      if (String(chatId) === env.ADMIN_CHAT_ID) {
        await recordAdminMessage(env, result.message_id).catch(() => {});
      }
      return result;
    },
  };
}

export async function handleUpdate(update, env) {
  const tg = wrapAdminMessageTracking(telegramApi(env.BOT_TOKEN), env);
  const ctx = { tg, env, getItems: makeItemsGetter(env) };

  if (update.message) {
    await handleMessage(update.message, ctx);
  } else if (update.callback_query) {
    // Only ever produced by a stale inline button from before this
    // bot stopped having interactive menus -- just send the same
    // welcome everyone else gets.
    try {
      await ctx.tg.answerCallbackQuery(update.callback_query.id);
    } catch (_err) {
      // expired -- harmless
    }
    await sendWelcome(update.callback_query.message.chat.id, ctx);
  }
}

async function getItemsOrNotify(ctx, chatId) {
  try {
    return await ctx.getItems();
  } catch (_err) {
    await ctx.tg.sendMessage(chatId, "Không tải được danh mục ngay lúc này, vui lòng thử lại sau.");
    return null;
  }
}

// Never trusts a name or price the client might have sent (there is
// no such field in our own payloads, but belt-and-suspenders) -- always
// re-looks-up the current catalog entry by code.
function buildOrderFromCodeQty(pairs, items) {
  const order = {};
  const droppedCodes = [];
  for (const { code, qty } of pairs) {
    const item = findByCode(items, code);
    if (!item) {
      droppedCodes.push(code);
      continue;
    }
    order[code] = (order[code] || 0) + qty;
  }
  return { order, droppedCodes };
}

// "/hangve" (lần 20): supplier-invoice photos sent in a SEPARATE group
// chat (the one used to manage the announcement channel), not the
// admin's own 1-1 chat with the bot. This bot does NOTHING ELSE in
// that chat -- no welcome message, no order parsing -- so an otherwise
// normal group conversation isn't interrupted by customer-facing
// replies every time someone posts something unrelated. Requires
// privacy mode OFF for this bot (a per-bot setting, applies everywhere
// it's a member, via @BotFather) so Telegram actually forwards photo
// messages at all -- see bot/README.md.
const SUPPLIER_PHOTO_COMMAND = "/hangve";

async function handleSupplierGroupMessage(message, ctx) {
  const { tg, env } = ctx;
  const chatId = message.chat.id;
  // A photo's caption and a plain message's text are different fields
  // -- checking both lets a text-only "/hangve" (sent with no photo
  // attached, by mistake) still match and get the explicit "no photo"
  // reply below, instead of silently doing nothing.
  const caption = (message.caption || message.text || "").trim();
  if (!caption.toLowerCase().startsWith(SUPPLIER_PHOTO_COMMAND)) {
    return; // not a match -- stay silent, this group has other traffic too
  }
  const note = caption.slice(SUPPLIER_PHOTO_COMMAND.length).trim();

  // Telegram sends several resolutions per photo, smallest first -- the
  // last one is the largest, which is what OCR/reading by eye needs.
  // A document (sent as "File" to skip Telegram's own re-compression,
  // which the owner may prefer for OCR accuracy) carries just one
  // file_id -- accepted too, but only jpeg/png: an iPhone's "Send as
  // File" can deliver image/heic, which Qt on the app side can't
  // decode (a blank image, OCR gets nothing, with no error shown) --
  // better to ask for a supported type up front than fail silently later.
  const DOCUMENT_MIME_TYPES = ["image/jpeg", "image/png"];
  let fileId, fileUniqueId;
  if (message.photo && message.photo.length > 0) {
    const largest = message.photo[message.photo.length - 1];
    fileId = largest.file_id;
    fileUniqueId = largest.file_unique_id;
  } else if (message.document && DOCUMENT_MIME_TYPES.includes(message.document.mime_type)) {
    fileId = message.document.file_id;
    fileUniqueId = message.document.file_unique_id;
  } else if (message.document) {
    await tg.sendMessage(chatId, 'Gửi dạng Ảnh (Photo) -- định dạng file này app chưa đọc được.');
    return;
  } else {
    await tg.sendMessage(
      chatId,
      'Chưa thấy ảnh đính kèm -- gửi kèm 1 ảnh (hoặc 1 file ảnh JPG/PNG) cùng với caption "/hangve".',
    );
    return;
  }

  try {
    const file = await tg.getFile(fileId);
    const bytes = await tg.downloadFile(file.file_path);
    await recordSupplierPhoto(env, {
      note,
      dataBase64: arrayBufferToBase64(bytes),
      messageDateSec: message.date,
      fileUniqueId,
    });
    await tg.sendMessage(
      chatId,
      'Đã nhận ảnh hóa đơn ✅ -- sẽ hiện trong app khi bạn mở lên và bấm "Đồng bộ ảnh từ Telegram".',
    );
  } catch (_err) {
    await tg.sendMessage(chatId, "Không lưu được ảnh này, thử gửi lại.");
  }
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const CHUNK = 0x8000; // String.fromCharCode(...bytes) on a huge array blows the call stack
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

async function handleMessage(message, ctx) {
  const { tg, env } = ctx;
  const chatId = message.chat.id;

  if (env.SUPPLIER_GROUP_CHAT_ID && String(chatId) === env.SUPPLIER_GROUP_CHAT_ID) {
    await handleSupplierGroupMessage(message, ctx);
    return;
  }

  // Any OTHER non-private chat -- a group this bot is a member of
  // before SUPPLIER_GROUP_CHAT_ID is configured, or any group it ends
  // up added to later -- gets silence from the customer-facing flow
  // below, except /myid (how the owner finds a group's chat id in the
  // first place, see bot/README.md mục 13). Without this, the moment
  // privacy mode is turned off (required for "/hangve" to work at all),
  // every unrelated message in an admin group -- including Telegram's
  // own "bot was added" service message, which has no .text -- would
  // trigger the customer welcome reply and keyboard. message.chat.type
  // is missing only in hand-built test fixtures, never in a real
  // Telegram update -- treated as private there so existing tests don't
  // need every fixture updated.
  const chatType = message.chat.type || "private";
  if (chatType !== "private") {
    const firstToken = (message.text || "").trim().split(/\s+/)[0];
    if (firstToken && firstToken.split("@")[0].toLowerCase() === "/myid") {
      await tg.sendMessage(chatId, `ID Telegram của chat này: ${chatId}`);
    }
    return;
  }

  if (env.ADMIN_CHAT_ID && String(chatId) === env.ADMIN_CHAT_ID) {
    await recordAdminMessage(env, message.message_id).catch(() => {});
  }

  // Forwarding a channel post into this private chat is how the owner
  // gets that channel's chat id for CHANNEL_CHAT_ID (lần 21) -- a
  // channel has no in-channel commands like /myid (channel posts
  // arrive as update.channel_post, which this bot never even
  // receives/handles), and posting one there would notify every
  // subscriber. Bot API 7.0+ uses forward_origin; forward_from_chat is
  // the older field some clients may still send -- checked as a
  // fallback, not instead of. Scoped to ADMIN_CHAT_ID only: the
  // channel now advertises seasonal products (lần 21), so a CUSTOMER
  // forwarding one of those announcements back to the bot is plausible
  // -- without this check they'd get a raw chat id instead of the
  // order button, which would look broken.
  const forwardedChannel =
    message.forward_origin?.type === "channel"
      ? message.forward_origin.chat
      : message.forward_from_chat?.type === "channel"
        ? message.forward_from_chat
        : null;
  if (forwardedChannel && env.ADMIN_CHAT_ID && String(chatId) === env.ADMIN_CHAT_ID) {
    await tg.sendMessage(chatId, `ID Telegram của kênh "${forwardedChannel.title}": ${forwardedChannel.id}`);
    return;
  }

  // A phone number shared in response to the checkout prompt -- only
  // trust it if it's the sender's own contact card, not one they
  // forwarded from someone else.
  if (message.contact && message.contact.user_id === message.from.id) {
    await finishCheckout(chatId, message.from, message.contact.phone_number, ctx, { remember: true });
    return;
  }

  const text = (message.text || "").trim();

  if (text === SKIP_PHONE_TEXT) {
    await finishCheckout(chatId, message.from, null, ctx, { remember: true });
    return;
  }

  // Submitted from the Mini App's "Xác nhận gửi đơn" button
  // (Telegram.WebApp.sendData() -- only possible when the Mini App was
  // opened from a keyboard `web_app` button, which is exactly what
  // orderKeyboard() sends). Arrives as a service message, not a normal
  // text message, so it's checked before the text-based branches below.
  if (message.web_app_data) {
    const pairs = parseWebAppOrderLines(message.web_app_data.data);
    if (pairs.length === 0) {
      await sendWelcome(chatId, ctx);
      return;
    }
    const items = await getItemsOrNotify(ctx, chatId);
    if (!items) return;
    const { order, droppedCodes } = buildOrderFromCodeQty(pairs, items);
    await processIncomingOrder(order, droppedCodes, items, message, ctx);
    return;
  }

  if (!text) {
    await sendWelcome(chatId, ctx);
    return;
  }

  const firstToken = text.split(/\s+/)[0];
  const command = firstToken.startsWith("/") ? firstToken.split("@")[0] : null;

  if (command === "/start" || command === "/help") {
    await sendWelcome(chatId, ctx);
    return;
  }
  if (command === "/myid") {
    await tg.sendMessage(chatId, `ID Telegram của bạn: ${chatId}`);
    return;
  }
  if (command === "/contact") {
    await tg.sendMessage(chatId, `Liên hệ trực tiếp người bán: ${env.CONTACT_URL}`);
    return;
  }
  if (command === "/doisdt") {
    await forgetCustomer(env, chatId);
    await tg.sendMessage(chatId, "Đã xóa thông tin cũ. Lần đặt hàng tiếp theo bot sẽ hỏi lại số điện thoại.", {
      reply_markup: await orderKeyboard(env, chatId),
    });
    return;
  }
  if (command === "/xoatinnhan") {
    // Admin-only: scoped to ADMIN_CHAT_ID's own tracked messages, so
    // even if a customer somehow typed this in their own chat, there's
    // nothing of theirs in the log to delete.
    if (!env.ADMIN_CHAT_ID || String(chatId) !== env.ADMIN_CHAT_ID) {
      await sendWelcome(chatId, ctx);
      return;
    }
    await deleteRecentAdminMessages(chatId, ctx);
    return;
  }
  if (command) {
    await sendWelcome(chatId, ctx);
    return;
  }

  // Not a command and not web_app_data: the only other thing this bot
  // understands is the website's own `CODE xQTY — Name` cart-text
  // format, used by customers who opened the site in a normal browser
  // (outside Telegram) and tapped "Gửi đơn qua Telegram" -- Telegram
  // itself only prefills that text, the customer still has to press
  // Send, which is exactly the manual step the Mini App button avoids.
  const codeLines = parseCodeOrderLines(text);
  if (codeLines.length === 0) {
    await sendWelcome(chatId, ctx);
    return;
  }

  const items = await getItemsOrNotify(ctx, chatId);
  if (!items) return;

  const { order, droppedCodes } = buildOrderFromCodeQty(codeLines, items);
  await processIncomingOrder(order, droppedCodes, items, message, ctx);
}

// Shared by both ways an order can arrive (website text paste or Mini
// App sendData): stores it as the one pending order for this chat, then
// either forwards it straight away (returning customer, already
// answered the phone/skip question once) or asks first (first time).
async function processIncomingOrder(order, droppedCodes, items, message, ctx) {
  const { tg, env } = ctx;
  const chatId = message.chat.id;

  const lines = orderLines(order, items);
  if (lines.length === 0) {
    await tg.sendMessage(
      chatId,
      'Không nhận diện được mặt hàng nào trong đơn này (có thể danh mục đã đổi). Vui lòng thử lại qua nút "🛒 Đặt hàng".',
    );
    return;
  }

  // Each incoming order is the WHOLE order -- replace, never merge
  // with whatever was pending before (a resend or an edited cart must
  // not double quantities).
  await setPendingOrder(env, chatId, order);

  const remembered = await getRememberedCustomer(env, chatId);
  if (remembered) {
    // No phone/skip prompt in between, so this confirmation is the
    // customer's ONLY look at what actually got sent -- it must show
    // the order itself, not just a bare "sent" acknowledgement. `lines`
    // is passed straight through (not re-read from KV) so this doesn't
    // depend on a read-after-write of the setPendingOrder() call just
    // above landing within the same request -- setPendingOrder() still
    // ran, so the order stays recoverable if the admin send fails.
    await finishCheckout(chatId, message.from, remembered.phone || null, ctx, { remember: false, droppedCodes, lines });
    return;
  }

  const { text: summary } = buildOrderText(lines);
  const parts = [summary];
  if (droppedCodes.length > 0) {
    parts.push("", `(Không nhận diện được: ${droppedCodes.join(", ")} -- có thể đã ngừng bán.)`);
  }
  parts.push("", "Để người bán liên hệ xác nhận đơn, vui lòng chia sẻ số điện thoại, hoặc bỏ qua để chỉ dùng Telegram:");

  await tg.sendMessage(chatId, parts.join("\n"), {
    reply_markup: {
      keyboard: [[{ text: "📞 Chia sẻ số điện thoại", request_contact: true }], [{ text: SKIP_PHONE_TEXT }]],
      resize_keyboard: true,
      one_time_keyboard: true,
    },
  });
}

// Telegram's own hard limit (not a bug, see README.md): a bot can only
// delete a message within 48h of it being sent, no exception. This
// deletes whatever in the tracked log still qualifies; anything older
// needs the admin's own "Xóa lịch sử trò chuyện" in their Telegram app.
async function deleteRecentAdminMessages(chatId, ctx) {
  const { tg, env } = ctx;
  const ids = await takeDeletableAdminMessages(env);
  if (ids.length === 0) {
    await tg.sendMessage(chatId, "Không có tin nhắn nào trong 48 giờ gần đây để xóa.", {
      reply_markup: await orderKeyboard(env, chatId),
    });
    return;
  }
  // deleteMessages takes at most 100 ids per call.
  for (let i = 0; i < ids.length; i += 100) {
    try {
      await tg.deleteMessages(chatId, ids.slice(i, i + 100));
    } catch (_err) {
      // A whole-batch failure (network, etc.) -- individual
      // undeletable ids inside a batch are skipped by Telegram, not
      // thrown, so this only fires for something more fundamental.
    }
  }
  await tg.sendMessage(chatId, `Đã dọn ${ids.length} tin nhắn trong 48 giờ gần nhất.`, {
    reply_markup: await orderKeyboard(env, chatId),
  });
}

async function finishCheckout(chatId, from, phone, ctx, { remember, droppedCodes = [], lines: precomputedLines } = {}) {
  const { tg, env } = ctx;
  let lines = precomputedLines;
  if (!lines) {
    const items = await getItemsOrNotify(ctx, chatId);
    if (!items) return;
    const order = await getPendingOrder(env, chatId);
    lines = orderLines(order, items);
  }

  if (lines.length === 0) {
    await tg.sendMessage(chatId, "Không có đơn nào đang chờ. Mời bạn đặt hàng qua website.", {
      reply_markup: await orderKeyboard(env, chatId),
    });
    return;
  }

  const label = from.username
    ? `${from.first_name || ""} (@${from.username})`.trim()
    : `${from.first_name || "Khách"} (id ${from.id})`;
  const { text } = buildOrderText(lines, { label, phone });

  // Written BEFORE attempting the admin Telegram message, and
  // regardless of whether that send succeeds below -- the whole point
  // of this second channel (the desktop app's "Đơn hàng online" tab)
  // is that it doesn't depend on the admin ever seeing/finding the
  // Telegram message. Best-effort: never blocks checkout on it.
  await recordSyncOrder(env, {
    telegram_chat_id: chatId,
    customer_label: label,
    customer_phone: phone || null,
    lines: lines.map(({ code, qty, item }) => ({ code, qty, name: item.name, price: item.price })),
    total_estimated: lines.reduce((sum, { item, qty }) => sum + item.price * qty, 0),
    created_at: new Date().toISOString(),
  }).catch((_err) => {});

  // Best-effort, same spirit as recordSyncOrder above: this only feeds
  // the "Đặt lại đơn trước" shortcut and "hay mua" badges on the
  // customer's NEXT visit (see orderHistory.js) -- never blocks or
  // affects checkout itself either way. The return value (not a
  // re-read) is what every orderKeyboard() call below this point uses,
  // since Workers KV only guarantees eventual (not read-your-own-write)
  // consistency -- the same trap already fixed once for the
  // remembered-customer path (lần 12).
  let history = null;
  try {
    history = await recordOrderHistory(env, chatId, lines.map(({ code, qty }) => ({ code, qty })));
  } catch (_err) {
    // Falls through with history = null -- orderKeyboard() below then
    // just builds the plain (non-personalized) URL instead.
  }

  if (!env.ADMIN_CHAT_ID) {
    await tg.sendMessage(
      chatId,
      `Không thể gửi đơn tự động lúc này. Vui lòng gửi nội dung dưới đây cho người bán qua ${env.CONTACT_URL}:\n\n${text}`,
      { reply_markup: await orderKeyboard(env, chatId, history) },
    );
    return;
  }

  try {
    await tg.sendMessage(env.ADMIN_CHAT_ID, text);
  } catch (_err) {
    // Most likely cause: the admin has never pressed /start on this
    // bot, so Telegram won't let the bot message them yet. The pending
    // order is deliberately left untouched so nothing is lost.
    await tg.sendMessage(
      chatId,
      `Không thể gửi đơn tự động lúc này. Vui lòng gửi nội dung dưới đây cho người bán qua ${env.CONTACT_URL}:\n\n${text}`,
      { reply_markup: await orderKeyboard(env, chatId, history) },
    );
    return;
  }

  // Only remember on a FRESH answer (contact shared / skip tapped),
  // never when this call itself came from the remembered shortcut --
  // otherwise a one-time "skip" could never be upgraded to a phone
  // number later without clearing KV by hand.
  if (remember) {
    await rememberCustomer(env, chatId, { phone: phone || null });
  }

  await clearPendingOrder(env, chatId);

  const confirmParts = ["Đã gửi đơn đặt hàng cho người bán ✅", "", text];
  if (droppedCodes.length > 0) {
    confirmParts.push("", `(Không nhận diện được: ${droppedCodes.join(", ")} -- có thể đã ngừng bán.)`);
  }
  confirmParts.push("", "Người bán sẽ liên hệ sớm để xác nhận.");

  await tg.sendMessage(chatId, confirmParts.join("\n"), { reply_markup: await orderKeyboard(env, chatId, history) });
}
