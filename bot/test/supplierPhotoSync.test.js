import { test } from "node:test";
import assert from "node:assert/strict";
import { recordSupplierPhoto, listSupplierPhotos } from "../src/supplierPhotoSync.js";

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

test("recordSupplierPhoto writes a photo: key that listSupplierPhotos finds, in chronological order", async () => {
  const env = makeEnv();
  // The key's chronological ordering comes from the message's own
  // `date` (seconds), passed in explicitly -- not from wall-clock time
  // -- so distinct dates are what make this deterministic, no sleep needed.
  await recordSupplierPhoto(env, { note: "first", dataBase64: "aGVsbG8=", messageDateSec: 1_000, fileUniqueId: "a" });
  await recordSupplierPhoto(env, { note: "second", dataBase64: "d29ybGQ=", messageDateSec: 2_000, fileUniqueId: "b" });

  const photos = await listSupplierPhotos(env);
  assert.deepEqual(
    photos.map((p) => p.note),
    ["first", "second"],
  );
  assert.ok(photos.every((p) => p.key.startsWith("photo:")));
  assert.equal(photos[0].data, "aGVsbG8=");
});

test("listSupplierPhotos with since only returns strictly-newer keys", async () => {
  const env = makeEnv();
  await recordSupplierPhoto(env, { note: "first", dataBase64: "a", messageDateSec: 1_000, fileUniqueId: "a" });
  const afterFirst = (await listSupplierPhotos(env))[0].key;
  await recordSupplierPhoto(env, { note: "second", dataBase64: "b", messageDateSec: 2_000, fileUniqueId: "b" });

  const onlyNew = await listSupplierPhotos(env, afterFirst);
  assert.deepEqual(
    onlyNew.map((p) => p.note),
    ["second"],
  );
});

test("a missing note defaults to an empty string, not undefined/null", async () => {
  const env = makeEnv();
  await recordSupplierPhoto(env, { dataBase64: "a", messageDateSec: 1_000, fileUniqueId: "a" });
  const photos = await listSupplierPhotos(env);
  assert.equal(photos[0].note, "");
});

test("recording the same message (same date + file_unique_id) twice overwrites, not duplicates -- a webhook retry must not double a photo", async () => {
  const env = makeEnv();
  await recordSupplierPhoto(env, { note: "first try", dataBase64: "a", messageDateSec: 1_000, fileUniqueId: "same" });
  await recordSupplierPhoto(env, { note: "retry", dataBase64: "a", messageDateSec: 1_000, fileUniqueId: "same" });

  const photos = await listSupplierPhotos(env);
  assert.equal(photos.length, 1);
  assert.equal(photos[0].note, "retry");
});
