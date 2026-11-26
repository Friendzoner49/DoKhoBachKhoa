import { test } from "node:test";
import assert from "node:assert/strict";
import { recordSyncOrder, listSyncOrders } from "../src/onlineOrdersSync.js";

function makeEnv() {
  const store = new Map();
  return {
    ORDER_KV: {
      async get(key) {
        return store.has(key) ? store.get(key) : null;
      },
      async put(key, value) {
        store.set(key, value);
      },
      async list({ prefix = "" } = {}) {
        const keys = [...store.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name }));
        return { keys, list_complete: true, cursor: undefined };
      },
      _store: store,
    },
  };
}

test("recordSyncOrder writes a sync: key that listSyncOrders finds, in chronological order", async () => {
  const env = makeEnv();
  await recordSyncOrder(env, { telegram_chat_id: 1, note: "first" });
  await recordSyncOrder(env, { telegram_chat_id: 2, note: "second" });

  const orders = await listSyncOrders(env);
  assert.deepEqual(
    orders.map((o) => o.note),
    ["first", "second"],
  );
  assert.ok(orders.every((o) => o.key.startsWith("sync:")));
});

test("listSyncOrders with since only returns strictly-newer keys", async () => {
  const env = makeEnv();
  await recordSyncOrder(env, { telegram_chat_id: 1, note: "first" });
  const afterFirst = (await listSyncOrders(env))[0].key;
  await recordSyncOrder(env, { telegram_chat_id: 2, note: "second" });

  const onlyNew = await listSyncOrders(env, afterFirst);
  assert.deepEqual(
    onlyNew.map((o) => o.note),
    ["second"],
  );
});

test("two orders in the same millisecond still get distinct keys", async () => {
  const env = makeEnv();
  await Promise.all([
    recordSyncOrder(env, { telegram_chat_id: 1, note: "a" }),
    recordSyncOrder(env, { telegram_chat_id: 1, note: "b" }),
  ]);
  const orders = await listSyncOrders(env);
  assert.equal(orders.length, 2);
  assert.notEqual(orders[0].key, orders[1].key);
});
