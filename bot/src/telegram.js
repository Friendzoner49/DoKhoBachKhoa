// Minimal Telegram Bot API client -- just the methods this bot uses.
// No library dependency: the API is plain HTTPS POST + JSON, and
// pulling in a full SDK isn't worth it for a handful of calls.
const API_BASE = "https://api.telegram.org";

export function telegramApi(token) {
  async function call(method, payload) {
    const res = await fetch(`${API_BASE}/bot${token}/${method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) {
      throw new Error(`Telegram ${method} failed: ${data.description || res.status}`);
    }
    return data.result;
  }

  return {
    sendMessage: (chat_id, text, extra = {}) => call("sendMessage", { chat_id, text, ...extra }),
    sendPhoto: (chat_id, photo, extra = {}) => call("sendPhoto", { chat_id, photo, ...extra }),
    answerCallbackQuery: (callback_query_id, extra = {}) =>
      call("answerCallbackQuery", { callback_query_id, ...extra }),
    // Up to 100 ids per call (Telegram's own limit); ids it can't
    // delete (already gone, or older than 48h) are silently skipped,
    // not treated as an error -- see adminMessageLog.js.
    deleteMessages: (chat_id, message_ids) => call("deleteMessages", { chat_id, message_ids }),
    // getFile only returns a file_path -- downloading the actual bytes
    // is a SEPARATE, non-JSON endpoint (see downloadFile below), unlike
    // every other method here.
    getFile: (file_id) => call("getFile", { file_id }),
    // "/hangve" (lần 20, supplier-invoice photos from the Telegram
    // group) downloads the real bytes via Telegram's file endpoint
    // (different base path from the Bot API above, still needs the
    // token). Returns an ArrayBuffer.
    downloadFile: async (file_path) => {
      const res = await fetch(`${API_BASE}/file/bot${token}/${file_path}`);
      if (!res.ok) {
        throw new Error(`Telegram file download failed: HTTP ${res.status}`);
      }
      return res.arrayBuffer();
    },
    // Channel announcements (lần 21) upload the image BYTES instead of
    // pointing sendPhoto at a public URL -- the natural click order is
    // "Cập nhật website giá" then "Đăng lên kênh", and GitHub Pages can
    // take anywhere from ~30s to a few minutes to actually serve a
    // freshly-pushed file, so a URL-based sendPhoto right after
    // publishing would race that deploy and fail with "can't fetch
    // photo". A raw upload has no such dependency. Separate from
    // `call()` above because this needs multipart/form-data, not JSON.
    sendPhotoUpload: async (chat_id, bytes, filename, extra = {}) => {
      const form = new FormData();
      form.append("chat_id", String(chat_id));
      for (const [key, value] of Object.entries(extra)) {
        form.append(key, String(value));
      }
      form.append("photo", new Blob([bytes]), filename);
      const res = await fetch(`${API_BASE}/bot${token}/sendPhoto`, { method: "POST", body: form });
      const data = await res.json();
      if (!data.ok) {
        throw new Error(`Telegram sendPhoto (upload) failed: ${data.description || res.status}`);
      }
      return data.result;
    },
  };
}
