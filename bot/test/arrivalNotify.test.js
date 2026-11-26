// Unit tests for sendArrivalMessages() itself -- per-chat success/
// failure needs finer control than flow.test.js's shared stubFetch
// (one fixed reply per Telegram METHOD, not per call), so this mocks
// fetch directly. The /notify/arrival ROUTE (auth, bad body, relay
// shape) is covered in flow.test.js alongside the other app<->Worker
// routes.
import { test } from "node:test";
import assert from "node:assert/strict";
import { sendArrivalMessages } from "../src/arrivalNotify.js";

function makeEnv(perChatOutcome) {
  return { BOT_TOKEN: "test-token", _perChatOutcome: perChatOutcome };
}

function stubPerChatFetch(perChatOutcome) {
  return async (url, init) => {
    const body = JSON.parse(init.body);
    const outcome = perChatOutcome(body.chat_id);
    if (outcome.throw) {
      return new Response(JSON.stringify({ ok: false, description: outcome.description }), { status: 400 });
    }
    return new Response(JSON.stringify({ ok: true, result: { message_id: 1 } }), { status: 200 });
  };
}

test("sendArrivalMessages reports ok:true for a chat Telegram accepted", async (t) => {
  t.mock.method(globalThis, "fetch", stubPerChatFetch(() => ({ throw: false })));
  const results = await sendArrivalMessages(makeEnv(), [{ chat_id: "111", text: "hi" }]);
  assert.deepEqual(results, [{ chat_id: "111", ok: true }]);
});

test("sendArrivalMessages isolates ONE chat's failure from the rest of the batch", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    stubPerChatFetch((chatId) =>
      chatId === "222" ? { throw: true, description: "Forbidden: bot was blocked by the user" } : { throw: false },
    ),
  );

  const results = await sendArrivalMessages(makeEnv(), [
    { chat_id: "111", text: "hi 111" },
    { chat_id: "222", text: "hi 222" },
    { chat_id: "333", text: "hi 333" },
  ]);

  assert.deepEqual(
    results.map((r) => [r.chat_id, r.ok]),
    [
      ["111", true],
      ["222", false],
      ["333", true],
    ],
  );
  assert.match(results[1].error, /blocked/);
});

test("sendArrivalMessages sends each customer only their own text", async (t) => {
  const seen = [];
  t.mock.method(globalThis, "fetch", async (url, init) => {
    seen.push(JSON.parse(init.body));
    return new Response(JSON.stringify({ ok: true, result: { message_id: 1 } }), { status: 200 });
  });

  await sendArrivalMessages(makeEnv(), [
    { chat_id: "111", text: "Hàng của bạn: Bún khô x2" },
    { chat_id: "222", text: "Hàng của bạn: Mắm Chinsu x1" },
  ]);

  assert.equal(seen[0].chat_id, "111");
  assert.match(seen[0].text, /Bún khô/);
  assert.equal(seen[1].chat_id, "222");
  assert.match(seen[1].text, /Mắm Chinsu/);
  assert.doesNotMatch(seen[0].text, /Mắm Chinsu/); // never leaks another customer's line
});
