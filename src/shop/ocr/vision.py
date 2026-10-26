"""Optional, better-than-Tesseract reading aid for supplier invoice
tables, using a local vision-language model through Ollama
(qwen2.5vl:7b) -- still fully offline, still free (no paid API, matches
CLAUDE.md's zero-cost rule).

Ollama is a separate one-time install (like Tesseract -- see CLAUDE.md
mục 2) that runs as a local server on 127.0.0.1:11434. This module never
auto-installs Ollama or auto-pulls the model: the model is ~6GB and
that's a deliberate choice for the user to make once, not something to
trigger silently from a button click.

This is a READING AID ONLY, same spirit as shop.ocr.engine -- it never
writes anything to supplier_invoice_lines by itself. The user still
reads the text and types the table by hand (see shop.core.supplier_invoices
for why: a hand-stamped invoice photo is never reliably perfect, and
auto-filling numbers that later turn out wrong would be invisible).

Compared with Tesseract: tested against real invoice photos (CLAUDE.md
lần 22), Tesseract only reads the header (invoice number/date/total)
reliably -- the item table comes back empty. qwen2.5vl:7b reads the
item table itself, with occasional transcription errors in item names
but quantity/price numbers that check out arithmetically
(qty * unit_price = line_total) on real test invoices. It's slower
(~15-20s/photo on CPU) and needs a 6GB download, so it stays an
optional *extra* button next to Tesseract, not a replacement.
"""
import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_MODEL = "qwen2.5vl:7b"
_GENERATE_URL = "http://127.0.0.1:11434/api/generate"
_PROMPT = (
    "This is a supplier invoice, text written in Russian (and sometimes "
    "unaccented Vietnamese). Transcribe EXACTLY every row of the items "
    "table (not the header, not the total) in order: item name, "
    "quantity, unit, unit price, line total. Keep the original text, do "
    "not translate, do not skip any row. Output as a numbered list."
)


class VisionOcrUnavailable(Exception):
    """Ollama isn't running, the model isn't pulled, or the call failed.
    Every caller must catch this and fall back to manual entry / plain
    Tesseract OCR -- there is no server-side fallback (would cost money
    and need internet)."""


def read_invoice_table(image_path: Path, model: str = DEFAULT_MODEL, timeout: float = 180.0) -> str:
    # 180s, not a tighter number: the model's first call after being idle
    # has to load ~6GB into VRAM first -- measured 95s for that alone on
    # this machine, before any actual reading starts.
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("ascii")
    payload = {
        "model": model,
        "prompt": _PROMPT,
        "images": [image_b64],
        "stream": False,
        "options": {
            "num_predict": 1536,
            # num_ctx raised from Ollama's 4096 default: a real invoice
            # photo alone can take over 4096 tokens, which fails outright
            # (HTTP 400) rather than just truncating -- confirmed against
            # real photos. The UI resizes the image before calling this
            # (see supplier_invoice_dialog.py) to keep well under this.
            "num_ctx": 8192,
            # A transcription task should be deterministic, not creative --
            # confirmed by testing: the same photo run twice at default
            # temperature produced two DIFFERENT wrong numbers (one
            # mis-read price each time), not the same error both times.
            "temperature": 0,
        },
    }
    req = urllib.request.Request(
        _GENERATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if "not found" in body.lower():
            raise VisionOcrUnavailable(
                f'Chưa tải model "{model}" trong Ollama. Mở terminal/PowerShell, chạy: '
                f"ollama pull {model} (khoảng 6GB, chỉ cần tải 1 lần)."
            ) from e
        raise VisionOcrUnavailable(f"Ollama trả về lỗi (HTTP {e.code}): {body}") from e
    except urllib.error.URLError as e:
        raise VisionOcrUnavailable(
            "Chưa chạy Ollama trên máy này. Cài miễn phí tại https://ollama.com, mở Ollama (chạy nền), "
            f"rồi chạy: ollama pull {model} (1 lần duy nhất, khoảng 6GB)."
        ) from e
    except (TimeoutError, OSError) as e:
        raise VisionOcrUnavailable(
            "Đọc ảnh quá lâu (máy chậm hoặc ảnh quá lớn) -- thử lại hoặc dùng \"Đọc chữ (OCR)\" thường."
        ) from e
    except ValueError as e:
        raise VisionOcrUnavailable(f"Ollama trả về dữ liệu không đọc được: {e}") from e
    text = data.get("response", "")
    if data.get("done_reason") == "length":
        text += (
            "\n\n⚠ CHƯA ĐỌC HẾT ẢNH (hết giới hạn độ dài trả lời) -- hóa đơn có thể còn dòng chưa hiện ra, "
            "đối chiếu kỹ với ảnh thật."
        )
    return text
