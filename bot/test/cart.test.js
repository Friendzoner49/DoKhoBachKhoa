import { test } from "node:test";
import assert from "node:assert/strict";
import { orderLines, buildOrderText, lineTotal } from "../src/cart.js";

test("orderLines drops codes no longer in the published catalog", () => {
  const items = [{ code: "A1", name: "Còn hàng", price: 100 }];
  const lines = orderLines({ A1: 1, DISCONTINUED: 3 }, items);
  assert.equal(lines.length, 1);
  assert.equal(lines[0].code, "A1");
});

test("buildOrderText matches the website's CODE xQTY — Name line format", () => {
  const items = [{ code: "BUN01", name: "Bún khô", price: 161 }];
  const lines = orderLines({ BUN01: 2 }, items);
  const { text, total } = buildOrderText(lines);
  assert.ok(text.includes("BUN01 x2 — Bún khô"));
  assert.equal(total, 322);
});

test("buildOrderText appends the customer label (and phone) after the total, never inside an item line", () => {
  const items = [{ code: "BUN01", name: "Bún khô", price: 161 }];
  const lines = orderLines({ BUN01: 1 }, items);
  const { text } = buildOrderText(lines, { label: "@someuser", phone: "+79990001122" });
  const rows = text.split("\n");
  const itemLineIndex = rows.findIndex((l) => l.startsWith("BUN01"));
  const customerLineIndex = rows.findIndex((l) => l.startsWith("Khách:"));
  const phoneLineIndex = rows.findIndex((l) => l.startsWith("SĐT:"));
  assert.ok(customerLineIndex > itemLineIndex);
  assert.ok(phoneLineIndex > customerLineIndex);
});

test("buildOrderText omits the SĐT line when no phone was shared", () => {
  const items = [{ code: "BUN01", name: "Bún khô", price: 161 }];
  const lines = orderLines({ BUN01: 1 }, items);
  const { text } = buildOrderText(lines, { label: "@someuser" });
  assert.ok(!text.includes("SĐT:"));
});

// 26/10/2026: the "Lấy sỉ" quick-add button must quote the SAME total
// the invoice will actually charge (shop.core.pricing.bulk_discount),
// not the plain price * qty -- mirrors shop.core.pricing.bulk_price's
// 118/25 -> 2891 example from the Python test suite.
test("lineTotal applies the bulk discount once qty reaches bulk_qty", () => {
  const item = { code: "GAO005", name: "Gạo", price: 118, bulk_qty: 25 };
  assert.equal(lineTotal(item, 25), 2891);
});

test("lineTotal charges the plain price below the bulk_qty threshold", () => {
  const item = { code: "GAO005", name: "Gạo", price: 118, bulk_qty: 25 };
  assert.equal(lineTotal(item, 24), 118 * 24);
});

test("lineTotal ignores bulk_qty for an item that doesn't have one", () => {
  const item = { code: "BUN01", name: "Bún khô", price: 161 };
  assert.equal(lineTotal(item, 100), 161 * 100);
});

test("buildOrderText's total reflects the bulk discount, not plain price * qty", () => {
  const items = [{ code: "GAO005", name: "Gạo", price: 118, bulk_qty: 25 }];
  const lines = orderLines({ GAO005: 25 }, items);
  const { total } = buildOrderText(lines);
  assert.equal(total, 2891);
});

// 27/10/2026 (lần 29): mirrors shop.core.pricing.bulk_discount's
// per-complete-tier formula -- a qty that crosses the threshold but
// ISN'T an exact multiple of bulk_qty only gets the sỉ rate on the
// complete tier(s); the leftover is plain-priced, not blanket-discounted.
test("lineTotal applies the sỉ rate per complete tier, not to the whole qty", () => {
  const item = { code: "GAO001", name: "Gạo Jasmin Aroy-D 4,5 Kg", price: 297, bulk_qty: 4.5 };
  // 1 bao (4.5kg) + 1kg loose -> 1310 (bulk_price) + 297 (plain 1kg).
  assert.equal(lineTotal(item, 5.5), 1607);
  // 2 full bao, no leftover.
  assert.equal(lineTotal(item, 9), 2620);
});
