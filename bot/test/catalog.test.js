import { test } from "node:test";
import assert from "node:assert/strict";
import { findByCode } from "../src/catalog.js";

test("findByCode", () => {
  const items = [{ code: "X" }, { code: "Y" }];
  assert.equal(findByCode(items, "Y").code, "Y");
  assert.equal(findByCode(items, "missing"), undefined);
});
