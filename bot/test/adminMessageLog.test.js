import { test } from "node:test";
import assert from "node:assert/strict";
import { recordAdminMessage, takeDeletableAdminMessages } from "../src/adminMessageLog.js";

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
      async delete(key) {
        store.delete(key);
      },
    },
  };
}

test("takeDeletableAdminMessages returns everything just recorded, and resets the log", async () => {
  const env = makeEnv();
  await recordAdminMessage(env, 101);
  await recordAdminMessage(env, 102);
  assert.deepEqual(await takeDeletableAdminMessages(env), [101, 102]);
  assert.deepEqual(await takeDeletableAdminMessages(env), []);
});

test("an id older than 48h is pruned and never comes back", async (t) => {
  const env = makeEnv();
  const base = Date.parse("2026-01-01T00:00:00Z");
  t.mock.method(Date, "now", () => base);
  await recordAdminMessage(env, 1);

  // 49 hours later: recording a new message prunes the stale one.
  t.mock.method(Date, "now", () => base + 49 * 60 * 60 * 1000);
  await recordAdminMessage(env, 2);

  assert.deepEqual(await takeDeletableAdminMessages(env), [2]);
});

test("recordAdminMessage ignores a falsy message id instead of logging garbage", async () => {
  const env = makeEnv();
  await recordAdminMessage(env, undefined);
  await recordAdminMessage(env, 0);
  assert.deepEqual(await takeDeletableAdminMessages(env), []);
});
