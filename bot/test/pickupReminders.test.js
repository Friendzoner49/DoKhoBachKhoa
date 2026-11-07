import { test } from "node:test";
import assert from "node:assert/strict";
import { registerPickups, markPickedUp, runPickupReminders, REMINDER_TEXT } from "../src/pickupReminders.js";

function fakeKv() {
  const store = new Map();
  return {
    store,
    async put(k, v) {
      store.set(k, v);
    },
    async get(k) {
      return store.has(k) ? store.get(k) : null;
    },
    async delete(k) {
      store.delete(k);
    },
    async list({ prefix }) {
      return { keys: [...store.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })), list_complete: true };
    },
  };
}

function fakeTg(failFor = new Set()) {
  const sent = [];
  return {
    sent,
    async sendMessage(chat_id, text, extra) {
      if (failFor.has(String(chat_id))) throw new Error("Forbidden: bot was blocked by the user");
      sent.push({ chat_id: String(chat_id), text, extra });
    },
  };
}

const HOUR = 3600 * 1000;
const T0 = Date.UTC(2026, 10, 6, 6, 0);

test("registerPickups stores only remind:true entries and sends ONE admin message with a button each", async () => {
  const env = { ORDER_KV: fakeKv(), ADMIN_CHAT_ID: "999" };
  const tg = fakeTg();
  await registerPickups(
    env,
    tg,
    [
      { order_id: 1, chat_id: "111", label: "An", remind: true },
      { order_id: 2, chat_id: "222", label: "Binh", remind: false },
      { order_id: 3, chat_id: "333", label: "Cuong", remind: true },
    ],
    T0,
  );
  assert.deepEqual([...env.ORDER_KV.store.keys()].sort(), ["pickup:1", "pickup:3"]);
  assert.equal(tg.sent.length, 1);
  assert.equal(tg.sent[0].chat_id, "999");
  const data = tg.sent[0].extra.reply_markup.inline_keyboard.map((r) => r[0].callback_data);
  assert.deepEqual(data, ["pk:1", "pk:3"]);
});

test("reminder goes out only at/after 24h, once", async () => {
  const env = { ORDER_KV: fakeKv(), ADMIN_CHAT_ID: "999" };
  await registerPickups(env, fakeTg(), [{ order_id: 1, chat_id: "111", label: "An", remind: true }], T0);

  const tg = fakeTg();
  assert.equal(await runPickupReminders(env, tg, T0 + 23 * HOUR), 0);
  assert.equal(await runPickupReminders(env, tg, T0 + 24 * HOUR), 1);
  assert.equal(tg.sent[0].chat_id, "111");
  assert.equal(tg.sent[0].text, REMINDER_TEXT);
  assert.equal(await runPickupReminders(env, tg, T0 + 30 * HOUR), 0); // never twice
  assert.equal(tg.sent.length, 1);
});

test("a customer marked picked-up gets no reminder", async () => {
  const env = { ORDER_KV: fakeKv(), ADMIN_CHAT_ID: "999" };
  await registerPickups(env, fakeTg(), [{ order_id: 1, chat_id: "111", label: "An", remind: true }], T0);
  assert.equal(await markPickedUp(env, "1"), true);
  const tg = fakeTg();
  assert.equal(await runPickupReminders(env, tg, T0 + 48 * HOUR), 0);
  assert.equal(tg.sent.length, 0);
});

test("a blocked customer is marked reminded, not retried every run", async () => {
  const env = { ORDER_KV: fakeKv(), ADMIN_CHAT_ID: "999" };
  await registerPickups(env, fakeTg(), [{ order_id: 1, chat_id: "111", label: "An", remind: true }], T0);
  const tg = fakeTg(new Set(["111"]));
  assert.equal(await runPickupReminders(env, tg, T0 + 25 * HOUR), 1);
  assert.equal(await runPickupReminders(env, tg, T0 + 26 * HOUR), 0);
  assert.match(JSON.parse(env.ORDER_KV.store.get("pickup:1")).error, /blocked/);
});

test("at most 40 reminders per run; the rest wait for the next run", async () => {
  const env = { ORDER_KV: fakeKv(), ADMIN_CHAT_ID: "999" };
  const many = Array.from({ length: 45 }, (_v, i) => ({ order_id: i + 1, chat_id: String(1000 + i), label: `K${i}`, remind: true }));
  await registerPickups(env, fakeTg(), many, T0);
  const tg = fakeTg();
  assert.equal(await runPickupReminders(env, tg, T0 + 25 * HOUR), 40);
  assert.equal(await runPickupReminders(env, tg, T0 + 26 * HOUR), 5);
});

test("only the admin's tap on ✅ removes the pending reminder", async (t) => {
  const { handleUpdate } = await import("../src/handlers.js");
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ ok: true, result: true }), { status: 200 }));
  const env = { ORDER_KV: fakeKv(), ADMIN_CHAT_ID: "999", BOT_TOKEN: "x" };
  await registerPickups(env, fakeTg(), [{ order_id: 7, chat_id: "111", label: "An", remind: true }], T0);
  const tap = (fromId) => ({
    update_id: 1,
    callback_query: {
      id: "q",
      from: { id: fromId },
      data: "pk:7",
      message: { message_id: 5, chat: { id: 999, type: "private" }, reply_markup: { inline_keyboard: [[{ callback_data: "pk:7" }]] } },
    },
  });
  await handleUpdate(tap(111), env); // a customer
  assert.ok(env.ORDER_KV.store.has("pickup:7"));
  await handleUpdate(tap(999), env); // the admin
  assert.ok(!env.ORDER_KV.store.has("pickup:7"));
});
