// End-to-end tests driving the actual Worker entry point (src/index.js)
// through handlers.js, orderStore.js and telegram.js -- the files the
// pure-function tests in cart.test.js / catalog.test.js / orderParser.test.js
// never touch. No real network and no real Cloudflare: `fetch` is
// stubbed, and ORDER_KV is a plain Map with the 3 methods the code uses.
import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";

const CATALOG = {
  updated_at: "2026-10-19T00:00:00Z",
  currency: "RUB",
  items: [
    { code: "BUN01", name: "Bún khô", unit: "gói", price: 161 },
    { code: "BADAV1", name: "Bánh Đa Nem Vuông Thanh Thủy", unit: "gói", price: 120 },
  ],
};

const WEBSITE_ORDER_TEXT = [
  "Đơn đặt hàng từ website:",
  "BUN01 x2 — Bún khô",
  "BADAV1 x1 — Bánh Đa Nem Vuông Thanh Thủy",
  "—",
  "Tổng ước tính: 442 ₽",
].join("\n");

function makeKv() {
  const store = new Map();
  return {
    async get(key) {
      return store.has(key) ? store.get(key) : null;
    },
    async put(key, value) {
      store.set(key, value);
    },
    async delete(key) {
      store.delete(key);
    },
    // Minimal stand-in for Cloudflare KV's list({prefix}) -- no
    // pagination (tests never need more than a handful of keys), just
    // enough shape (`keys`, `list_complete`) for onlineOrdersSync.js.
    async list({ prefix = "" } = {}) {
      const keys = [...store.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name }));
      return { keys, list_complete: true, cursor: undefined };
    },
    _store: store,
  };
}

function makeEnv(overrides = {}) {
  return {
    BOT_TOKEN: "test-token",
    WEBHOOK_SECRET: "test-secret",
    CATALOG_URL: "https://example.test/products.json",
    SITE_BASE_URL: "https://example.test/",
    CONTACT_URL: "https://t.me/sellertest",
    ORDER_KV: makeKv(),
    ...overrides,
  };
}

function stubFetch(calls, telegramReplies = {}) {
  let nextMessageId = 1;
  return async (url, init) => {
    const href = typeof url === "string" ? url : url.toString();
    if (href.includes("example.test/products.json")) {
      return new Response(JSON.stringify(CATALOG), { status: 200 });
    }
    // Telegram's binary file-download endpoint (/file/bot<token>/...) --
    // a different URL shape from the JSON Bot API below, used by
    // getFile/downloadFile for "/hangve" (lần 20).
    if (href.includes("/file/bot")) {
      calls.push({ method: "downloadFile", url: href });
      const bytes = telegramReplies.downloadFile?.bytes || new Uint8Array([0xff, 0xd8, 0xff, 1, 2, 3]);
      return new Response(bytes, { status: 200 });
    }
    if (href.includes("api.telegram.org")) {
      const method = href.split("/").pop();
      // sendPhotoUpload (lần 21) posts multipart/form-data, not JSON --
      // flatten it into a plain object for assertions, keeping the
      // photo Blob itself so a test can check its size/bytes.
      let body;
      if (init?.body instanceof FormData) {
        body = {};
        for (const [key, value] of init.body.entries()) body[key] = value;
      } else {
        body = init?.body ? JSON.parse(init.body) : {};
      }
      calls.push({ method, body });
      const reply = telegramReplies[method];
      if (reply?.throw) {
        return new Response(JSON.stringify({ ok: false, description: reply.description }), { status: 400 });
      }
      const result = method === "sendMessage" ? { message_id: nextMessageId++ } : reply?.result || {};
      return new Response(JSON.stringify({ ok: true, result }), { status: 200 });
    }
    throw new Error(`Unexpected fetch: ${href}`);
  };
}

function telegramUpdate(overrides) {
  return { update_id: 1, ...overrides };
}

function post(env, update, secret = "test-secret") {
  return worker.fetch(
    new Request("https://example.test/", {
      method: "POST",
      headers: { "X-Telegram-Bot-Api-Secret-Token": secret, "content-type": "application/json" },
      body: JSON.stringify(update),
    }),
    env,
    {},
  );
}

function getSyncOrders(env, secret, since) {
  const qs = since ? `?since=${encodeURIComponent(since)}` : "";
  return worker.fetch(
    new Request(`https://example.test/sync/orders${qs}`, {
      method: "GET",
      headers: secret != null ? { "X-Sync-Secret": secret } : {},
    }),
    env,
    {},
  );
}

function getSyncPhotos(env, secret, since) {
  const qs = since ? `?since=${encodeURIComponent(since)}` : "";
  return worker.fetch(
    new Request(`https://example.test/sync/photos${qs}`, {
      method: "GET",
      headers: secret != null ? { "X-Sync-Secret": secret } : {},
    }),
    env,
    {},
  );
}

function postChannelAnnounce(env, secret, body) {
  return worker.fetch(
    new Request("https://example.test/channel/announce", {
      method: "POST",
      headers: {
        ...(secret != null ? { "X-Sync-Secret": secret } : {}),
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
    }),
    env,
    {},
  );
}

function postNotifyArrival(env, secret, body) {
  return worker.fetch(
    new Request("https://example.test/notify/arrival", {
      method: "POST",
      headers: {
        ...(secret != null ? { "X-Sync-Secret": secret } : {}),
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
    }),
    env,
    {},
  );
}

test("a wrong webhook secret is rejected with 403 and never calls Telegram", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv();
  const res = await post(env, telegramUpdate({ message: { chat: { id: 1 }, text: "/start", from: { id: 1 } } }), "wrong");
  assert.equal(res.status, 403);
  assert.equal(calls.length, 0);
});

test("a missing WEBHOOK_SECRET fails closed (never silently accepts)", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ WEBHOOK_SECRET: undefined });
  const res = await post(env, telegramUpdate({ message: { chat: { id: 1 }, text: "/start", from: { id: 1 } } }));
  assert.equal(res.status, 403);
  assert.equal(calls.length, 0);
});

test("/start gives the customer a persistent web_app keyboard button, not a menu", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv();
  await post(env, telegramUpdate({ message: { chat: { id: 1 }, text: "/start", from: { id: 1 } } }));
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent);
  assert.equal(sent.body.reply_markup.keyboard[0][0].web_app.url, env.SITE_BASE_URL);
});

test("plain text that isn't the website's order format also gets the website keyboard", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv();
  await post(env, telegramUpdate({ message: { chat: { id: 1 }, text: "Tôi muốn đặt 2 chai nước mắm", from: { id: 1 } } }));
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent.body.reply_markup.keyboard[0][0].web_app.url);
});

test("an unrecognized callback_query (from a message sent before this bot stopped having menus) gets the keyboard too", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv();
  await post(env, telegramUpdate({ callback_query: { id: "cb1", data: "cat:0", message: { chat: { id: 1 } }, from: { id: 1 } } }));
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent.body.reply_markup.keyboard[0][0].web_app.url);
});

test("/myid and /contact reply without ever fetching the catalog", async (t) => {
  const calls = [];
  const fetchStub = async (url, init) => {
    const href = typeof url === "string" ? url : url.toString();
    if (href.includes("products.json")) throw new Error("should not fetch the catalog for /myid or /contact");
    if (href.includes("api.telegram.org")) {
      calls.push(JSON.parse(init?.body || "{}"));
      return new Response(JSON.stringify({ ok: true, result: {} }), { status: 200 });
    }
    throw new Error(`unexpected fetch ${href}`);
  };
  t.mock.method(globalThis, "fetch", fetchStub);
  const env = makeEnv();
  const res1 = await post(env, telegramUpdate({ message: { chat: { id: 42 }, text: "/myid", from: { id: 42 } } }));
  assert.equal(res1.status, 200);
  assert.ok(calls.some((c) => c.text.includes("42")));

  const res2 = await post(env, telegramUpdate({ message: { chat: { id: 42 }, text: "/contact", from: { id: 42 } } }));
  assert.equal(res2.status, 200);
  assert.ok(calls.some((c) => c.text.includes(env.CONTACT_URL)));
});

// How the owner gets CHANNEL_CHAT_ID (lần 21): a channel has no
// in-channel /myid (channel posts never reach this bot's handler, and
// posting there would notify every subscriber) -- forwarding one post
// into the bot's private chat is the private alternative.
test("the admin forwarding a channel post to the bot's private chat replies with that channel's id", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  const res = await post(
    env,
    telegramUpdate({
      message: {
        chat: { id: 999 },
        from: { id: 999 },
        forward_origin: { type: "channel", chat: { id: -1001234567890, title: "Đồ khô Bách Khoa" }, date: 1 },
      },
    }),
  );
  assert.equal(res.status, 200);
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.match(sent.body.text, /-1001234567890/);
  assert.match(sent.body.text, /Đồ khô Bách Khoa/);
});

test("the admin forwarding a channel post via the older forward_from_chat field also works", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  await post(
    env,
    telegramUpdate({
      message: {
        chat: { id: 999 },
        from: { id: 999 },
        forward_from_chat: { type: "channel", id: -1009876543210, title: "Đồ khô Bách Khoa" },
      },
    }),
  );
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.match(sent.body.text, /-1009876543210/);
});

test("a customer forwarding a channel post (seasonal-product announcement) gets the order keyboard, not a raw chat id", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" }); // customer chat id (42) is NOT the admin
  await post(
    env,
    telegramUpdate({
      message: {
        chat: { id: 42 },
        from: { id: 42 },
        forward_origin: { type: "channel", chat: { id: -1001234567890, title: "Đồ khô Bách Khoa" }, date: 1 },
      },
    }),
  );
  const sent = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === 42);
  assert.ok(sent.body.reply_markup.keyboard, "should get the normal order keyboard, not a channel-id reply");
  assert.doesNotMatch(sent.body.text, /-1001234567890/);
});

test("a website order message replaces the pending order and prompts for a phone in the SAME reply -- no extra /cart step", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv();
  const chatId = 7;

  await post(env, telegramUpdate({ message: { chat: { id: chatId }, from: { id: chatId }, text: WEBSITE_ORDER_TEXT } }));

  assert.deepEqual(JSON.parse(env.ORDER_KV._store.get(`order:${chatId}`)), { BUN01: 2, BADAV1: 1 });
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent.body.text.includes("BUN01 x2 — Bún khô"));
  assert.ok(sent.body.reply_markup.keyboard, "expected the phone/skip reply keyboard on the very first reply");
});

test("sending the same website order twice does not double the quantities", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv();
  const chatId = 13;

  await post(env, telegramUpdate({ message: { chat: { id: chatId }, from: { id: chatId }, text: WEBSITE_ORDER_TEXT } }));
  await post(env, telegramUpdate({ message: { chat: { id: chatId }, from: { id: chatId }, text: WEBSITE_ORDER_TEXT } }));

  assert.deepEqual(JSON.parse(env.ORDER_KV._store.get(`order:${chatId}`)), { BUN01: 2, BADAV1: 1 });
});

test("a code the catalog no longer has is reported as dropped, not silently ignored", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv();
  const text = ["BUN01 x1 — Bún khô", "GONE01 x1 — Đã ngừng bán", "—", "Tổng ước tính: 161 ₽"].join("\n");
  await post(env, telegramUpdate({ message: { chat: { id: 20 }, from: { id: 20 }, text } }));
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent.body.text.includes("GONE01"));
});

test("checkout keeps the order and tells the customer, if the admin send fails (admin never pressed /start)", async (t) => {
  const calls = [];
  const fetchStub = async (url, init) => {
    const href = typeof url === "string" ? url : url.toString();
    if (href.includes("products.json")) return new Response(JSON.stringify(CATALOG), { status: 200 });
    if (href.includes("api.telegram.org")) {
      const method = href.split("/").pop();
      const body = init?.body ? JSON.parse(init.body) : {};
      calls.push({ method, body });
      if (method === "sendMessage" && body.chat_id === "999") {
        return new Response(JSON.stringify({ ok: false, description: "chat not found" }), { status: 400 });
      }
      return new Response(JSON.stringify({ ok: true, result: {} }), { status: 200 });
    }
    throw new Error(`Unexpected fetch: ${href}`);
  };
  t.mock.method(globalThis, "fetch", fetchStub);
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  const chatId = 8;
  await env.ORDER_KV.put(`order:${chatId}`, JSON.stringify({ BUN01: 1 }));

  await post(
    env,
    telegramUpdate({
      message: { chat: { id: chatId }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: chatId, first_name: "Khach" } },
    }),
  );

  assert.ok(env.ORDER_KV._store.has(`order:${chatId}`), "a failed admin send must not lose the customer's order");
  const toCustomer = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === chatId);
  assert.ok(toCustomer, "the customer must still get a reply when the admin send fails");
  assert.ok(toCustomer.body.text.includes(env.CONTACT_URL));
});

test("checkout with no ADMIN_CHAT_ID configured gives the customer a fallback instead of silently failing", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv(); // no ADMIN_CHAT_ID
  const chatId = 9;
  await env.ORDER_KV.put(`order:${chatId}`, JSON.stringify({ BUN01: 1 }));

  await post(
    env,
    telegramUpdate({
      message: { chat: { id: chatId }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: chatId, first_name: "Khach" } },
    }),
  );

  const fallback = calls.find((c) => c.method === "sendMessage" && c.body.text.includes(env.CONTACT_URL));
  assert.ok(fallback);
});

function webAppUpdate(chatId, lines) {
  return telegramUpdate({
    message: {
      chat: { id: chatId },
      from: { id: chatId, first_name: "Khach" },
      web_app_data: { data: JSON.stringify({ lines }), button_text: "🛒 Đặt hàng" },
    },
  });
}

test("a Mini App order (web_app_data) still asks for a phone the first time, same as a website-text order", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  const chatId = 30;

  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 2 }]));

  assert.deepEqual(JSON.parse(env.ORDER_KV._store.get(`order:${chatId}`)), { BUN01: 2 });
  const sent = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === chatId);
  assert.ok(sent.body.reply_markup.keyboard.some((row) => row.some((btn) => btn.request_contact)));
  assert.ok(!calls.some((c) => c.method === "sendMessage" && c.body.chat_id === "999"), "must not forward before the phone question is answered");
});

test("once a customer has answered the phone question, later Mini App orders forward with zero prompts", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  const chatId = 31;

  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 1 }]));
  await post(
    env,
    telegramUpdate({
      message: { chat: { id: chatId }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: chatId, first_name: "Khach" } },
    }),
  );
  calls.length = 0; // only care about what happens from here on

  await post(env, webAppUpdate(chatId, [{ code: "BADAV1", qty: 3 }]));

  const toAdmin = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === "999");
  assert.ok(toAdmin, "the second order must reach the admin with no extra round trip");
  assert.ok(toAdmin.body.text.includes("BADAV1 x3"));
  const toCustomer = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === chatId);
  assert.ok(!toCustomer.body.reply_markup.keyboard.some((row) => row.some((btn) => btn.request_contact)), "must not ask again");
  assert.ok(toCustomer.body.reply_markup.keyboard[0][0].web_app, "the order button must come back for next time");
  assert.ok(
    toCustomer.body.text.includes("BADAV1 x3"),
    "this confirmation is the customer's ONLY look at the order (no prompt happened in between), so it must show what was actually sent",
  );
});

test("a remembered customer's auto-forward still reports a dropped (discontinued) code, not just a bare confirmation", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  const chatId = 34;

  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 1 }]));
  await post(
    env,
    telegramUpdate({
      message: { chat: { id: chatId }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: chatId, first_name: "Khach" } },
    }),
  );
  calls.length = 0;

  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 1 }, { code: "GONE01", qty: 2 }]));

  const toCustomer = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === chatId);
  assert.ok(toCustomer.body.text.includes("BUN01"));
  assert.ok(toCustomer.body.text.includes("GONE01"));
});

test("/doisdt forgets the remembered answer so the next order asks again", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  const chatId = 32;

  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 1 }]));
  await post(
    env,
    telegramUpdate({
      message: { chat: { id: chatId }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: chatId, first_name: "Khach" } },
    }),
  );
  await post(env, telegramUpdate({ message: { chat: { id: chatId }, text: "/doisdt", from: { id: chatId } } }));
  calls.length = 0;

  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 1 }]));

  const toCustomer = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === chatId);
  assert.ok(toCustomer.body.reply_markup.keyboard.some((row) => row.some((btn) => btn.request_contact)), "must ask again after /doisdt");
});

test("malformed web_app_data data falls back to the website keyboard instead of throwing", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv();
  const res = await post(
    env,
    telegramUpdate({
      message: { chat: { id: 33 }, from: { id: 33 }, web_app_data: { data: "not json", button_text: "x" } },
    }),
  );
  assert.equal(res.status, 200);
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent.body.reply_markup.keyboard[0][0].web_app.url);
});

test("sharing a phone number includes it in the order sent to the admin, and clears the pending order", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  const chatId = 10;
  await env.ORDER_KV.put(`order:${chatId}`, JSON.stringify({ BUN01: 1 }));

  await post(
    env,
    telegramUpdate({
      message: {
        chat: { id: chatId },
        from: { id: chatId, first_name: "Khach" },
        contact: { phone_number: "+79990001122", user_id: chatId },
      },
    }),
  );

  const toAdmin = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === "999");
  assert.ok(toAdmin.body.text.includes("SĐT: +79990001122"));
  assert.ok(!env.ORDER_KV._store.has(`order:${chatId}`));
});

test("/xoatinnhan (admin only) batch-deletes tracked admin-chat messages and reports how many", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });

  // A couple of order forwards land in the admin's chat...
  await post(env, webAppUpdate(999, [{ code: "BUN01", qty: 1 }]));
  await post(
    env,
    telegramUpdate({ message: { chat: { id: 999 }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: 999, first_name: "Admin" } } }),
  );
  calls.length = 0;

  await post(env, telegramUpdate({ message: { chat: { id: 999 }, text: "/xoatinnhan", from: { id: 999 } } }));

  const deleteCall = calls.find((c) => c.method === "deleteMessages");
  assert.ok(deleteCall, "expected a deleteMessages call");
  assert.equal(deleteCall.body.chat_id, 999);
  assert.ok(deleteCall.body.message_ids.length > 0);
  const confirm = calls.find((c) => c.method === "sendMessage" && c.body.text.includes("Đã dọn"));
  assert.ok(confirm);
});

test("/xoatinnhan does nothing (just the usual keyboard) for anyone other than the admin", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });

  await post(env, telegramUpdate({ message: { chat: { id: 5 }, text: "/xoatinnhan", from: { id: 5 } } }));

  assert.ok(!calls.some((c) => c.method === "deleteMessages"));
});

test("GET /sync/orders rejects a missing or wrong secret, and never touches KV", async (t) => {
  const env = makeEnv({ SYNC_SECRET: "sync-secret" });
  const noSecretRes = await getSyncOrders(env, null);
  assert.equal(noSecretRes.status, 403);
  const wrongSecretRes = await getSyncOrders(env, "nope");
  assert.equal(wrongSecretRes.status, 403);
});

test("GET /sync/orders fails closed when SYNC_SECRET isn't configured at all", async (t) => {
  const env = makeEnv(); // no SYNC_SECRET
  const res = await getSyncOrders(env, "anything");
  assert.equal(res.status, 403);
});

function supplierPhotoUpdate(chatId, caption, { date = 1_761_000_000, fileUniqueId = "l1", asDocument = false } = {}) {
  return telegramUpdate({
    message: {
      chat: { id: chatId, type: "supergroup" },
      from: { id: chatId, first_name: "Quan ly" },
      date,
      caption,
      ...(asDocument
        ? { document: { file_id: "doc1", file_unique_id: fileUniqueId, mime_type: "image/jpeg" } }
        : {
            photo: [
              { file_id: "small", file_unique_id: "s1", width: 90, height: 90 },
              { file_id: "large", file_unique_id: fileUniqueId, width: 1600, height: 1200 },
            ],
          }),
    },
  });
}

test("a photo with \"/hangve\" caption in the supplier group is saved and acknowledged", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls, { getFile: { result: { file_path: "photos/file_1.jpg" } } }));
  const env = makeEnv({ SUPPLIER_GROUP_CHAT_ID: "555", SYNC_SECRET: "sync-secret" });

  await post(env, supplierPhotoUpdate(555, "/hangve đợt về 25/10, thiếu BUN01"));

  // Used the LARGEST photo size, not the thumbnail.
  const getFileCall = calls.find((c) => c.method === "getFile");
  assert.equal(getFileCall.body.file_id, "large");
  const downloadCall = calls.find((c) => c.method === "downloadFile");
  assert.ok(downloadCall.url.includes("photos/file_1.jpg"));

  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent.body.text.includes("Đã nhận ảnh"));

  const res = await getSyncPhotos(env, "sync-secret");
  const { photos } = await res.json();
  assert.equal(photos.length, 1);
  assert.equal(photos[0].note, "đợt về 25/10, thiếu BUN01");
  assert.ok(photos[0].data); // base64 bytes present
});

test("the supplier group bot stays silent for anything that isn't a /hangve photo (no customer-facing replies)", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ SUPPLIER_GROUP_CHAT_ID: "555" });

  // Plain chat text -- must NOT get the usual "sendWelcome" keyboard;
  // this is an internal group, not a customer-facing chat.
  await post(env, telegramUpdate({ message: { chat: { id: 555 }, text: "họp lúc 3h nhé", from: { id: 1 } } }));
  assert.equal(calls.length, 0);

  // A photo with no caption, or a caption that isn't the command.
  await post(env, supplierPhotoUpdate(555, undefined));
  await post(env, supplierPhotoUpdate(555, "ảnh vui thôi"));
  assert.equal(calls.length, 0);
});

test("GET /sync/photos rejects a missing or wrong secret", async (t) => {
  const env = makeEnv({ SYNC_SECRET: "sync-secret" });
  assert.equal((await getSyncPhotos(env, null)).status, 403);
  assert.equal((await getSyncPhotos(env, "nope")).status, 403);
});

test("GET /sync/photos with since only returns strictly newer photos", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls, { getFile: { result: { file_path: "p.jpg" } } }));
  const env = makeEnv({ SUPPLIER_GROUP_CHAT_ID: "555", SYNC_SECRET: "sync-secret" });

  // Keys are built from the message's own `date` (see supplierPhotoSync.js),
  // so distinct dates -- not a real-time sleep -- is what makes the
  // ordering deterministic here.
  await post(env, supplierPhotoUpdate(555, "/hangve first", { date: 1_761_000_000, fileUniqueId: "f1" }));
  const firstKey = (await (await getSyncPhotos(env, "sync-secret")).json()).photos[0].key;
  await post(env, supplierPhotoUpdate(555, "/hangve second", { date: 1_761_000_100, fileUniqueId: "f2" }));

  const onlyNew = (await (await getSyncPhotos(env, "sync-secret", firstKey)).json()).photos;
  assert.deepEqual(
    onlyNew.map((p) => p.note),
    ["second"],
  );
});

test("the SAME Telegram webhook redelivery (same message) overwrites one KV entry, not two", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls, { getFile: { result: { file_path: "p.jpg" } } }));
  const env = makeEnv({ SUPPLIER_GROUP_CHAT_ID: "555", SYNC_SECRET: "sync-secret" });

  const update = supplierPhotoUpdate(555, "/hangve retry test", { date: 1_761_000_200, fileUniqueId: "same-file" });
  await post(env, update);
  await post(env, update); // Telegram retries on a timeout -- identical update_id/message

  const { photos } = await (await getSyncPhotos(env, "sync-secret")).json();
  assert.equal(photos.length, 1);
});

test("/hangve sent as a File (document) is accepted, not just Photo", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls, { getFile: { result: { file_path: "d.jpg" } } }));
  const env = makeEnv({ SUPPLIER_GROUP_CHAT_ID: "555", SYNC_SECRET: "sync-secret" });

  await post(env, supplierPhotoUpdate(555, "/hangve as file", { asDocument: true }));

  const { photos } = await (await getSyncPhotos(env, "sync-secret")).json();
  assert.equal(photos.length, 1);
});

test("/hangve sent as a HEIC file is rejected with a clear reply, not silently saved as unreadable", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ SUPPLIER_GROUP_CHAT_ID: "555" });

  await post(
    env,
    telegramUpdate({
      message: {
        chat: { id: 555, type: "supergroup" },
        from: { id: 555 },
        date: 1_761_000_500,
        caption: "/hangve iphone file",
        document: { file_id: "heic1", file_unique_id: "h1", mime_type: "image/heic" },
      },
    }),
  );

  assert.equal(calls.filter((c) => c.method === "getFile").length, 0); // never even tried to download it
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent.body.text.includes("Gửi dạng Ảnh"));
});

test("/hangve with no photo or document attached gets an explicit reply, not silence", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ SUPPLIER_GROUP_CHAT_ID: "555" });

  await post(
    env,
    telegramUpdate({
      message: { chat: { id: 555, type: "supergroup" }, from: { id: 555 }, date: 1_761_000_300, text: "/hangve quên gửi ảnh" },
    }),
  );

  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent);
  assert.ok(sent.body.text.includes("Chưa thấy ảnh"));
});

test("a group the bot is a member of (not the supplier group) stays silent except /myid -- e.g. Telegram's own \"bot added\" service message", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ SUPPLIER_GROUP_CHAT_ID: "555" }); // a DIFFERENT group, id 777, is not this one

  // Telegram's "bot was added to group" service message has no .text.
  await post(
    env,
    telegramUpdate({
      message: { chat: { id: 777, type: "group" }, from: { id: 1 }, date: 1_761_000_400, new_chat_members: [{ id: 999 }] },
    }),
  );
  assert.equal(calls.length, 0);

  // Ordinary group chatter must not get the customer welcome keyboard.
  await post(
    env,
    telegramUpdate({ message: { chat: { id: 777, type: "group" }, from: { id: 1 }, date: 1_761_000_401, text: "ai đi lấy hàng hôm nay" } }),
  );
  assert.equal(calls.length, 0);

  // /myid still works, so the owner can find a NEW group's chat id.
  await post(env, telegramUpdate({ message: { chat: { id: 777, type: "group" }, from: { id: 1 }, date: 1_761_000_402, text: "/myid" } }));
  const sent = calls.find((c) => c.method === "sendMessage");
  assert.ok(sent.body.text.includes("777"));
});

test("a checkout writes a sync record the app can pull, independent of whether the admin Telegram send succeeds", async (t) => {
  const calls = [];
  const fetchStub = async (url, init) => {
    const href = typeof url === "string" ? url : url.toString();
    if (href.includes("products.json")) return new Response(JSON.stringify(CATALOG), { status: 200 });
    if (href.includes("api.telegram.org")) {
      const method = href.split("/").pop();
      const body = init?.body ? JSON.parse(init.body) : {};
      calls.push({ method, body });
      if (method === "sendMessage" && body.chat_id === "999") {
        return new Response(JSON.stringify({ ok: false, description: "chat not found" }), { status: 400 });
      }
      return new Response(JSON.stringify({ ok: true, result: { message_id: 1 } }), { status: 200 });
    }
    throw new Error(`Unexpected fetch: ${href}`);
  };
  t.mock.method(globalThis, "fetch", fetchStub);
  const env = makeEnv({ ADMIN_CHAT_ID: "999", SYNC_SECRET: "sync-secret" });
  const chatId = 40;

  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 2 }]));
  await post(
    env,
    telegramUpdate({ message: { chat: { id: chatId }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: chatId, first_name: "Khach" } } }),
  );

  const res = await getSyncOrders(env, "sync-secret");
  assert.equal(res.status, 200);
  const { orders } = await res.json();
  assert.equal(orders.length, 1);
  assert.equal(orders[0].telegram_chat_id, chatId);
  assert.deepEqual(orders[0].lines, [{ code: "BUN01", qty: 2, name: "Bún khô", price: 161 }]);
  assert.equal(orders[0].total_estimated, 322);
});

test("after a completed order, the order button's URL carries a reorder shortcut for that same customer only", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  const chatId = 50;

  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 2 }, { code: "BADAV1", qty: 1 }]));
  await post(
    env,
    telegramUpdate({ message: { chat: { id: chatId }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: chatId, first_name: "Khach" } } }),
  );
  calls.length = 0;

  await post(env, telegramUpdate({ message: { chat: { id: chatId }, text: "/start", from: { id: chatId } } }));
  const sent = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === chatId);
  const url = new URL(sent.body.reply_markup.keyboard[0][0].web_app.url);
  assert.equal(url.searchParams.get("last"), "BUN01:2,BADAV1:1");
  // Not "hay mua" yet -- that needs a SECOND separate order with the
  // same code (see orderHistory.js's MIN_ORDERS_FOR_TOP), so one order
  // alone must not carry a `top` hint.
  assert.equal(url.searchParams.get("top"), null);

  // A different, brand-new customer must not see any of this.
  const other = await post(env, telegramUpdate({ message: { chat: { id: 51 }, text: "/start", from: { id: 51 } } }));
  assert.equal(other.status, 200);
  const sentOther = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === 51);
  assert.equal(sentOther.body.reply_markup.keyboard[0][0].web_app.url, env.SITE_BASE_URL);
});

test("a code only becomes a \"hay mua\" (top) hint after a SECOND separate order containing it", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999" });
  const chatId = 52;

  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 1 }]));
  await post(env, telegramUpdate({ message: { chat: { id: chatId }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: chatId } } }));
  await post(env, webAppUpdate(chatId, [{ code: "BUN01", qty: 1 }]));
  calls.length = 0;

  await post(env, telegramUpdate({ message: { chat: { id: chatId }, text: "/start", from: { id: chatId } } }));
  const sent = calls.find((c) => c.method === "sendMessage" && c.body.chat_id === chatId);
  const url = new URL(sent.body.reply_markup.keyboard[0][0].web_app.url);
  assert.equal(url.searchParams.get("top"), "BUN01");
});

test("GET /sync/orders with since only returns strictly newer orders", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ ADMIN_CHAT_ID: "999", SYNC_SECRET: "sync-secret" });

  await post(env, webAppUpdate(41, [{ code: "BUN01", qty: 1 }]));
  await post(env, telegramUpdate({ message: { chat: { id: 41 }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: 41 } } }));

  const first = await (await getSyncOrders(env, "sync-secret")).json();
  assert.equal(first.orders.length, 1);
  const cursor = first.orders[0].key;

  await post(env, webAppUpdate(42, [{ code: "BADAV1", qty: 1 }]));
  await post(env, telegramUpdate({ message: { chat: { id: 42 }, text: "Bỏ qua, chỉ dùng Telegram", from: { id: 42 } } }));

  const second = await (await getSyncOrders(env, "sync-secret", cursor)).json();
  assert.equal(second.orders.length, 1);
  assert.equal(second.orders[0].telegram_chat_id, 42);
});

// Seasonal products pushed from the app (lần 21) -- the app sends an
// already-formatted caption + public image URL, this route just
// relays to sendPhoto on CHANNEL_CHAT_ID. Same SYNC_SECRET as the two
// pull routes above.
// A tiny base64 payload stands in for "the product photo's bytes" --
// these tests only care that it round-trips through the Worker to
// sendPhotoUpload, not that it's a real JPEG.
const SAMPLE_IMAGE_BASE64 = btoa("fake-jpeg-bytes");

test("POST /channel/announce rejects a missing or wrong secret", async (t) => {
  const env = makeEnv({ SYNC_SECRET: "sync-secret", CHANNEL_CHAT_ID: "@dokhobachkhoa" });
  const body = { code: "RUOU01", caption: "hi", imageBase64: SAMPLE_IMAGE_BASE64, filename: "RUOU01.jpg" };
  assert.equal((await postChannelAnnounce(env, null, body)).status, 403);
  assert.equal((await postChannelAnnounce(env, "nope", body)).status, 403);
});

test("POST /channel/announce fails clearly when CHANNEL_CHAT_ID isn't configured", async (t) => {
  const env = makeEnv({ SYNC_SECRET: "sync-secret" });
  const res = await postChannelAnnounce(env, "sync-secret", {
    code: "RUOU01",
    caption: "hi",
    imageBase64: SAMPLE_IMAGE_BASE64,
    filename: "RUOU01.jpg",
  });
  assert.equal(res.status, 500);
});

test("POST /channel/announce uploads the given caption and image bytes to CHANNEL_CHAT_ID", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ SYNC_SECRET: "sync-secret", CHANNEL_CHAT_ID: "@dokhobachkhoa" });

  const res = await postChannelAnnounce(env, "sync-secret", {
    code: "RUOU01",
    caption: "🆕 Rượu Vodka\n1.070 RUB",
    imageBase64: SAMPLE_IMAGE_BASE64,
    filename: "RUOU01.jpg",
  });
  assert.equal(res.status, 200);

  const sendPhoto = calls.find((c) => c.method === "sendPhoto");
  assert.equal(sendPhoto.body.chat_id, "@dokhobachkhoa");
  assert.match(sendPhoto.body.caption, /Rượu Vodka/);
  assert.ok(sendPhoto.body.photo instanceof Blob);
  assert.equal(await sendPhoto.body.photo.text(), "fake-jpeg-bytes");
});

test("POST /channel/announce surfaces a Telegram send failure as a distinct status", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls, { sendPhoto: { throw: true, description: "wrong chat id" } }));
  const env = makeEnv({ SYNC_SECRET: "sync-secret", CHANNEL_CHAT_ID: "@dokhobachkhoa" });

  const res = await postChannelAnnounce(env, "sync-secret", {
    code: "RUOU01",
    caption: "hi",
    imageBase64: SAMPLE_IMAGE_BASE64,
    filename: "RUOU01.jpg",
  });
  assert.equal(res.status, 502);
});

// "Hàng đã về" DMs (request 25/10/2026) -- the app builds each
// customer's own text (shop.core.arrival_notify) and POSTs a batch;
// this route is a thin relay, so these tests focus on auth/shape, not
// message content (arrivalNotify.test.js covers per-chat behavior).

test("POST /notify/arrival rejects a missing or wrong secret", async (t) => {
  const env = makeEnv({ SYNC_SECRET: "sync-secret" });
  const body = { messages: [{ chat_id: "111", text: "hi" }] };
  assert.equal((await postNotifyArrival(env, null, body)).status, 403);
  assert.equal((await postNotifyArrival(env, "nope", body)).status, 403);
});

test("POST /notify/arrival rejects a body without a messages array", async (t) => {
  const env = makeEnv({ SYNC_SECRET: "sync-secret" });
  assert.equal((await postNotifyArrival(env, "sync-secret", {})).status, 400);
});

test("POST /notify/arrival relays each message and reports per-chat results", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", stubFetch(calls));
  const env = makeEnv({ SYNC_SECRET: "sync-secret" });

  const res = await postNotifyArrival(env, "sync-secret", {
    messages: [
      { chat_id: "111", text: "Hàng của bạn: Bún khô x2" },
      { chat_id: "222", text: "Hàng của bạn: Mắm Chinsu x1" },
    ],
  });

  assert.equal(res.status, 200);
  const data = await res.json();
  assert.deepEqual(
    data.results.map((r) => [r.chat_id, r.ok]),
    [
      ["111", true],
      ["222", true],
    ],
  );
  const sent = calls.filter((c) => c.method === "sendMessage");
  assert.equal(sent.length, 2);
  assert.equal(sent[0].body.chat_id, "111");
  assert.match(sent[0].body.text, /Bún khô/);
});
