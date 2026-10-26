import { sendArrivalMessages } from "./arrivalNotify.js";
import { handleUpdate } from "./handlers.js";
import { listSyncOrders } from "./onlineOrdersSync.js";
import { listSupplierPhotos } from "./supplierPhotoSync.js";
import { telegramApi } from "./telegram.js";

export default {
  async fetch(request, env, _ctx) {
    const url = new URL(request.url);

    // Pulled by the desktop app, not Telegram -- a completely separate
    // route/secret from the webhook below (see CLAUDE.md section 7,
    // lần 13). Checked by pathname before anything else so it never
    // falls through to the webhook's Telegram-update parsing.
    if (url.pathname === "/sync/orders") {
      if (request.method !== "GET") {
        return new Response("Method Not Allowed", { status: 405 });
      }
      const got = request.headers.get("X-Sync-Secret");
      if (!env.SYNC_SECRET || got !== env.SYNC_SECRET) {
        // A query-string secret would show up in `wrangler tail` logs
        // and browser history -- header only.
        return new Response("Forbidden", { status: 403 });
      }
      const since = url.searchParams.get("since") || undefined;
      const orders = await listSyncOrders(env, since);
      return new Response(JSON.stringify({ orders }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }

    // Supplier-invoice photos sent via "/hangve" in the group (lần 20)
    // -- same auth, same pull-not-push shape as /sync/orders above
    // (SYNC_SECRET is shared between the two; one credential for
    // "the desktop app talks to this Worker", not a separate one per
    // endpoint).
    if (url.pathname === "/sync/photos") {
      if (request.method !== "GET") {
        return new Response("Method Not Allowed", { status: 405 });
      }
      const got = request.headers.get("X-Sync-Secret");
      if (!env.SYNC_SECRET || got !== env.SYNC_SECRET) {
        return new Response("Forbidden", { status: 403 });
      }
      const since = url.searchParams.get("since") || undefined;
      const photos = await listSupplierPhotos(env, since);
      return new Response(JSON.stringify({ photos }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }

    // Pushed BY the desktop app (lần 21, seasonal products) to announce
    // a limited-time item on the public channel ("Đồ khô Bách Khoa").
    // Same SYNC_SECRET auth as the two pull routes above -- one
    // credential for "the app talks to this Worker". The app sends the
    // already-formatted caption and the image's raw bytes (base64) --
    // NOT a public URL: sendPhoto-by-URL would race GitHub Pages'
    // deploy delay right after "Cập nhật website giá", and silently
    // show a stale cached photo after a re-post with a swapped image.
    // This route doesn't touch the catalog or KV at all, just relays
    // the upload to Telegram.
    if (url.pathname === "/channel/announce") {
      if (request.method !== "POST") {
        return new Response("Method Not Allowed", { status: 405 });
      }
      const got = request.headers.get("X-Sync-Secret");
      if (!env.SYNC_SECRET || got !== env.SYNC_SECRET) {
        return new Response("Forbidden", { status: 403 });
      }
      if (!env.CHANNEL_CHAT_ID) {
        return new Response(JSON.stringify({ error: "CHANNEL_CHAT_ID chưa được cài đặt trên Worker." }), {
          status: 500,
          headers: { "content-type": "application/json" },
        });
      }
      let body;
      try {
        body = await request.json();
      } catch (_err) {
        return new Response("Bad Request", { status: 400 });
      }
      if (!body.imageBase64 || !body.caption) {
        return new Response("Bad Request", { status: 400 });
      }
      try {
        const binary = atob(body.imageBase64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const tg = telegramApi(env.BOT_TOKEN);
        await tg.sendPhotoUpload(env.CHANNEL_CHAT_ID, bytes, body.filename || "product.jpg", {
          caption: body.caption,
        });
      } catch (err) {
        console.error("channel/announce sendPhoto failed:", err);
        return new Response(JSON.stringify({ error: String(err.message || err) }), {
          status: 502,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }

    // Pushed BY the desktop app (request 25/10/2026) once the owner
    // links a closed order batch to the supplier invoice(s) that
    // fulfil it -- "hàng đã về" DMs, one per customer, each only
    // listing that customer's own lines (CLAUDE.md section 6's privacy
    // rule -- shop.core.arrival_notify builds the text, this route
    // never sees the catalog or anyone else's order). Same SYNC_SECRET
    // auth as the other app<->Worker routes above.
    if (url.pathname === "/notify/arrival") {
      if (request.method !== "POST") {
        return new Response("Method Not Allowed", { status: 405 });
      }
      const got = request.headers.get("X-Sync-Secret");
      if (!env.SYNC_SECRET || got !== env.SYNC_SECRET) {
        return new Response("Forbidden", { status: 403 });
      }
      let body;
      try {
        body = await request.json();
      } catch (_err) {
        return new Response("Bad Request", { status: 400 });
      }
      if (!Array.isArray(body.messages)) {
        return new Response("Bad Request", { status: 400 });
      }
      const results = await sendArrivalMessages(env, body.messages);
      return new Response(JSON.stringify({ results }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }

    if (request.method !== "POST") {
      // Visiting the Worker's URL directly (e.g. a health check) --
      // never a real Telegram update.
      return new Response("OK", { status: 200 });
    }

    // Telegram echoes back whatever secret_token was set on
    // setWebhook, on every request -- rejects anything else before it
    // touches the catalog fetch or KV. Fail CLOSED: a forgotten
    // WEBHOOK_SECRET must reject every request, not silently accept
    // them (that would let anyone spam the admin / burn the KV write
    // quota by POSTing fake updates straight to the Worker's public
    // URL). See README.md step 6.
    const got = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (!env.WEBHOOK_SECRET || got !== env.WEBHOOK_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }

    let update;
    try {
      update = await request.json();
    } catch (_err) {
      return new Response("Bad Request", { status: 400 });
    }

    try {
      await handleUpdate(update, env);
    } catch (err) {
      // Telegram retries webhook deliveries that don't return 200, so
      // a bug here must never turn into a retry storm -- log and still
      // answer OK.
      console.error("handleUpdate failed:", err);
    }

    return new Response("OK", { status: 200 });
  },
};
