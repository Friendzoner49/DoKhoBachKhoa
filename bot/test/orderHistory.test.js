import { test } from "node:test";
import assert from "node:assert/strict";
import { getOrderHistory, recordOrderHistory, topCodes, buildPersonalizedSiteUrl } from "../src/orderHistory.js";

function makeKv() {
  const store = new Map();
  return {
    async get(key) {
      return store.has(key) ? store.get(key) : null;
    },
    async put(key, value) {
      store.set(key, value);
    },
  };
}

test("recordOrderHistory remembers the last order and counts separate orders per code, not quantity", async () => {
  const env = { ORDER_KV: makeKv() };
  await recordOrderHistory(env, 1, [{ code: "BUN01", qty: 2 }, { code: "BADAV1", qty: 1 }]);
  await recordOrderHistory(env, 1, [{ code: "BUN01", qty: 10 }]); // a big single order must not inflate the count

  const history = await getOrderHistory(env, 1);
  assert.deepEqual(history.lastOrder, [{ code: "BUN01", qty: 10 }]);
  assert.deepEqual(history.frequency, { BUN01: 2, BADAV1: 1 });
});

test("recordOrderHistory returns the updated history directly, for callers that can't rely on a KV read-after-write", async () => {
  const env = { ORDER_KV: makeKv() };
  const history = await recordOrderHistory(env, 1, [{ code: "BUN01", qty: 2 }]);
  assert.deepEqual(history, { lastOrder: [{ code: "BUN01", qty: 2 }], frequency: { BUN01: 1 } });
});

test("a duplicate code within the SAME order only counts as one order toward its frequency", async () => {
  const env = { ORDER_KV: makeKv() };
  const history = await recordOrderHistory(env, 1, [{ code: "BUN01", qty: 1 }, { code: "BUN01", qty: 1 }]);
  assert.equal(history.frequency.BUN01, 1);
});

test("recordOrderHistory keeps each chat's history separate", async () => {
  const env = { ORDER_KV: makeKv() };
  await recordOrderHistory(env, 1, [{ code: "BUN01", qty: 2 }]);
  await recordOrderHistory(env, 2, [{ code: "BADAV1", qty: 5 }]);

  assert.equal((await getOrderHistory(env, 1)).frequency.BUN01, 1);
  assert.equal((await getOrderHistory(env, 2)).frequency.BADAV1, 1);
  assert.equal(await getOrderHistory(env, 999), null);
});

test("topCodes excludes a code only ever ordered once -- that's just the last order, not a repeat-purchase signal", () => {
  const history = { frequency: { A: 1, B: 3 } };
  assert.deepEqual(topCodes(history), ["B"]);
});

test("topCodes ranks by how many separate orders contained the code, most first", () => {
  const history = { frequency: { A: 2, B: 9, C: 4 } };
  assert.deepEqual(topCodes(history), ["B", "C", "A"]);
});

test("topCodes caps at the given limit", () => {
  const history = { frequency: { A: 2, B: 3, C: 4, D: 5 } };
  assert.deepEqual(topCodes(history, 2), ["D", "C"]);
});

test("topCodes handles no history (new customer) without throwing", () => {
  assert.deepEqual(topCodes(null), []);
  assert.deepEqual(topCodes({}), []);
});

test("buildPersonalizedSiteUrl returns the base URL unchanged for a brand new customer", () => {
  assert.equal(buildPersonalizedSiteUrl("https://example.test/", null), "https://example.test/");
});

test("buildPersonalizedSiteUrl encodes the last order and top codes as query params", () => {
  const history = { lastOrder: [{ code: "BUN01", qty: 2 }], frequency: { BUN01: 2, BADAV1: 5 } };
  const url = buildPersonalizedSiteUrl("https://example.test/", history);
  const parsed = new URL(url);
  assert.equal(parsed.origin + parsed.pathname, "https://example.test/");
  assert.equal(parsed.searchParams.get("last"), "BUN01:2");
  assert.equal(parsed.searchParams.get("top"), "BADAV1,BUN01");
});

test("buildPersonalizedSiteUrl omits `last` entirely once the last order is empty, and never crashes on a missing frequency map", () => {
  const url = buildPersonalizedSiteUrl("https://example.test/", { lastOrder: [] });
  assert.equal(url, "https://example.test/");
});

test("buildPersonalizedSiteUrl caps the number of last-order items it encodes", () => {
  const lastOrder = Array.from({ length: 50 }, (_, i) => ({ code: `C${i}`, qty: 1 }));
  const url = buildPersonalizedSiteUrl("https://example.test/", { lastOrder });
  const parsed = new URL(url);
  const items = parsed.searchParams.get("last").split(",");
  assert.ok(items.length <= 40, `expected at most 40 items, got ${items.length}`);
});
