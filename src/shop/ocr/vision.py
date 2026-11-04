"""Reading aid for supplier invoice tables, using a local vision-language
model through Ollama (qwen2.5vl:7b) -- fully offline, free (no paid API,
matches CLAUDE.md's zero-cost rule). This is the ONLY reading aid in the
app (Tesseract OCR was removed lần 31 -- CLAUDE.md -- real-world testing
on photographed invoices showed Tesseract only reads the header
reliably, the item table always comes back empty; the vision model reads
the item table itself, so there was nothing left for Tesseract to add).

Ollama is a separate one-time install (see CLAUDE.md mục 2) that runs as
a local server on 127.0.0.1:11434. This module never auto-installs
Ollama or auto-pulls the model: the model is ~6GB and that's a
deliberate choice for the user to make once, not something to trigger
silently from a button click.

This is a READING AID ONLY -- it never writes anything to
supplier_invoice_lines by itself. The caller (supplier_invoice_dialog's
"Nhập vào đơn", lần 31/việc 3) still inserts rows as an editable DRAFT
that the user must review/match/apply, same spirit as
shop.core.supplier_invoices for why: a hand-stamped invoice photo is
never reliably perfect, and silently trusting numbers that later turn
out wrong would be invisible.

Tested against real invoice photos: qwen2.5vl:7b reads the item table
with occasional transcription errors in item names, but quantity/price
numbers that check out arithmetically (qty * unit_price = line_total) on
real test invoices. It's slower (~15-20s/photo on CPU/GPU) and needs a
6GB download -- stays an optional button, not something run automatically.
"""
import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_MODEL = "qwen2.5vl:7b"
_GENERATE_URL = "http://127.0.0.1:11434/api/generate"

# One structured call, not two (advisor, lần 31/việc 3): the old version
# of this module did a free-text read for display, and a UI that wanted
# to pre-fill the table would otherwise need a SECOND ~15-30s call (plus
# the model's cold-load time if idle) just to get the same table again
# in a parseable shape. Ask for JSON straight away; the caller renders a
# human-readable numbered list FROM the parsed rows for the on-screen
# preview, so there's still something to read even when parsing fails.
_PROMPT = (
    "This is a photo of a supplier invoice. Each row of the items table "
    "has TWO names printed together: a Russian/Cyrillic description, "
    "AND a separate Vietnamese or English Latin-alphabet product name "
    "(often with a size like 200gr or 400g). Transcribe BOTH EXACTLY AS "
    "PRINTED on the page -- do NOT translate the Russian into English, "
    "do NOT paraphrase, do NOT invent a description. If you cannot find "
    "separate Latin text for a row, repeat the Russian text in both "
    "fields instead of inventing an English translation. Read every row "
    "of the items table (not the header, not the total), in order.\n"
    "Respond with ONLY a JSON object, no other text, no markdown code "
    "fence, in this exact shape:\n"
    '{"rows": [{"name_ru": "<Cyrillic text exactly as printed>", '
    '"name_latin": "<Latin-alphabet text exactly as printed, same row>", '
    '"qty": <number>, "unit": "<unit as printed, e.g. шт, кор, кг>", '
    '"unit_price": <number>, "line_total": <number>}]}'
)
_LEADING_ROW_NUMBER_RE = re.compile(r"^\s*\d+[.\s]+")


class VisionOcrUnavailable(Exception):
    """Ollama isn't running, the model isn't pulled, or the call failed.
    Every caller must catch this and fall back to manual entry -- there
    is no server-side fallback (would cost money and need internet)."""


class VisionOcrParseError(VisionOcrUnavailable):
    """The model responded, but its output wasn't parseable rows (bad
    JSON, truncated by num_predict, or missing the expected shape).
    Callers must treat this as "insert nothing" -- never insert a
    partial table silently missing rows the model ran out of room for."""


def _parse_number(value) -> float:
    """Ollama's JSON mode sometimes still renders a number as a string
    with a space thousands-separator and/or comma decimal (locale habits
    leaking from the invoice itself, e.g. "1 234,50") -- tolerate both,
    rather than letting int()/float() raise on the whole response."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", " ").replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    return float(text)


def _extract_json_object(text: str) -> str:
    # Defensive against the model wrapping its JSON in a ```json fence
    # despite being told not to (observed occasionally on real photos).
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


def read_invoice_rows(image_path: Path, model: str = DEFAULT_MODEL, timeout: float = 180.0) -> list[dict]:
    """Returns a list of dicts: name_ru, name_latin, qty, unit,
    unit_price, line_total. Raises VisionOcrParseError (never returns a
    partial list) if the model's response didn't parse cleanly or was
    cut short -- the caller must not insert anything in that case."""
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
        "format": "json",
        "options": {
            # Raised from the old free-text value (1536): each row now
            # carries both a Cyrillic AND a Latin name plus JSON
            # punctuation, so the same invoice needs more tokens than
            # the old numbered-list format did.
            "num_predict": 2048,
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
            "Đọc ảnh quá lâu (máy chậm hoặc ảnh quá lớn) -- thử lại hoặc chọn ảnh nhỏ hơn."
        ) from e
    except ValueError as e:
        raise VisionOcrUnavailable(f"Ollama trả về dữ liệu không đọc được: {e}") from e

    response_text = data.get("response", "")
    if data.get("done_reason") == "length":
        raise VisionOcrParseError(
            "⚠ CHƯA ĐỌC HẾT ẢNH (hết giới hạn độ dài trả lời) -- hóa đơn có thể còn dòng chưa hiện ra. "
            "Không nhập vào đơn để tránh thiếu dòng -- hãy gõ tay, hoặc thử ảnh cắt gọn hơn.\n\n"
            f"Văn bản đọc được (chưa đầy đủ):\n{response_text}"
        )
    try:
        parsed = json.loads(_extract_json_object(response_text))
        raw_rows = parsed["rows"]
        if not isinstance(raw_rows, list):
            raise TypeError("rows is not a list")
        rows = []
        for raw_row in raw_rows:
            # The model sometimes echoes the invoice's own row number into
            # the name text ("3 Сомбо...") despite not being asked to --
            # strip it, it's not part of the product name and would
            # pollute both raw_name_ru and suggest_matches' word overlap.
            name_ru = _LEADING_ROW_NUMBER_RE.sub("", str(raw_row.get("name_ru") or "").strip())
            name_latin = _LEADING_ROW_NUMBER_RE.sub("", str(raw_row.get("name_latin") or "").strip())
            rows.append(
                {
                    "name_ru": name_ru,
                    "name_latin": name_latin,
                    "qty": _parse_number(raw_row.get("qty")),
                    "unit": str(raw_row.get("unit") or "").strip(),
                    "unit_price": _parse_number(raw_row.get("unit_price")),
                    "line_total": _parse_number(raw_row.get("line_total")),
                }
            )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        raise VisionOcrParseError(
            f"AI trả về dữ liệu không đọc được dạng bảng ({e}). Không nhập vào đơn -- hãy gõ tay.\n\n"
            f"Văn bản AI trả về:\n{response_text}"
        ) from e
    return rows
