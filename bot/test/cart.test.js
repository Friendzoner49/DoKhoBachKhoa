import { test } from "node:test";
import assert from "node:assert/strict";
import { orderLines, buildOrderText } from "../src/cart.js";

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
