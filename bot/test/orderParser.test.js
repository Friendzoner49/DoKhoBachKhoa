import { test } from "node:test";
import assert from "node:assert/strict";
import { parseCodeOrderLines, parseWebAppOrderLines } from "../src/orderParser.js";

test("parseCodeOrderLines reads the website's exact cart-text format, ignoring header/footer lines", () => {
  const text = [
    "Đơn đặt hàng từ website:",
    "BUN01 x2 — Bún khô",
    "BADAV1 x1 — Bánh Đa Nem Vuông Thanh Thủy",
    "—",
    "Tổng ước tính: 442 ₽",
  ].join("\n");
  assert.deepEqual(parseCodeOrderLines(text), [
    { code: "BUN01", qty: 2 },
    { code: "BADAV1", qty: 1 },
  ]);
});

test("parseCodeOrderLines returns nothing for ordinary free text", () => {
  assert.deepEqual(parseCodeOrderLines("Tôi muốn đặt 2 chai nước mắm chinsu"), []);
});

test("parseCodeOrderLines returns nothing for an empty message", () => {
  assert.deepEqual(parseCodeOrderLines(""), []);
});

test("parseWebAppOrderLines reads the Mini App's {lines:[{code,qty}]} payload", () => {
  const raw = JSON.stringify({ lines: [{ code: "BUN01", qty: 2 }, { code: "BADAV1", qty: 1 }] });
  assert.deepEqual(parseWebAppOrderLines(raw), [
    { code: "BUN01", qty: 2 },
    { code: "BADAV1", qty: 1 },
  ]);
});

test("parseWebAppOrderLines clamps a bogus or absurd qty instead of trusting it", () => {
  const raw = JSON.stringify({ lines: [{ code: "A", qty: 0 }, { code: "B", qty: -5 }, { code: "C", qty: 999999 }] });
  assert.deepEqual(parseWebAppOrderLines(raw), [
    { code: "A", qty: 1 },
    { code: "B", qty: 1 },
    { code: "C", qty: 9999 },
  ]);
});

test("parseWebAppOrderLines returns nothing for malformed JSON or the wrong shape", () => {
  assert.deepEqual(parseWebAppOrderLines("not json"), []);
  assert.deepEqual(parseWebAppOrderLines(JSON.stringify({ lines: "nope" })), []);
  assert.deepEqual(parseWebAppOrderLines(JSON.stringify({})), []);
  assert.deepEqual(parseWebAppOrderLines(JSON.stringify({ lines: [{ qty: 2 }, { code: "" }, { code: 5, qty: 2 }] })), []);
});
