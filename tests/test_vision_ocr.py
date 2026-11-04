import json
import urllib.error

import pytest

from shop.ocr.vision import VisionOcrParseError, VisionOcrUnavailable, read_invoice_rows


class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(payload):
    def _open(req, timeout=None):
        return _FakeResponse(payload)

    return _open


def _ollama_json_response(rows):
    return {"response": json.dumps({"rows": rows})}


def test_read_invoice_rows_parses_the_models_json_response(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"not a real image, just needs to exist")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen(
            _ollama_json_response(
                [
                    {
                        "name_ru": "Рыбный соус CHINSU 250мл",
                        "name_latin": "Nuoc mam CHINSU 250ml",
                        "qty": 2,
                        "unit": "chai",
                        "unit_price": 150.0,
                        "line_total": 300.0,
                    }
                ]
            )
        ),
    )
    rows = read_invoice_rows(image)
    assert len(rows) == 1
    assert rows[0]["name_latin"] == "Nuoc mam CHINSU 250ml"
    assert rows[0]["name_ru"] == "Рыбный соус CHINSU 250мл"
    assert rows[0]["qty"] == 2.0
    assert rows[0]["unit_price"] == 150.0


def test_read_invoice_rows_strips_a_leading_row_number_the_model_echoed(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen(
            _ollama_json_response(
                [{"name_ru": "3 Сомбок с морепродуктами", "name_latin": "3 Sombock", "qty": 3, "unit": "шт", "unit_price": 42, "line_total": 126}]
            )
        ),
    )
    rows = read_invoice_rows(image)
    assert rows[0]["name_ru"] == "Сомбок с морепродуктами"
    assert rows[0]["name_latin"] == "Sombock"


def test_read_invoice_rows_tolerates_locale_formatted_numbers(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen(
            _ollama_json_response(
                [{"name_ru": "x", "name_latin": "x", "qty": "1", "unit": "шт", "unit_price": "1 234,50", "line_total": "1234.50"}]
            )
        ),
    )
    rows = read_invoice_rows(image)
    assert rows[0]["unit_price"] == 1234.50


def test_read_invoice_rows_wraps_connection_refused_in_a_vietnamese_message(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")

    def _raise(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    with pytest.raises(VisionOcrUnavailable, match="Ollama"):
        read_invoice_rows(image)


def test_read_invoice_rows_wraps_a_missing_model_in_a_vietnamese_message(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")

    def _raise_with_body(req, timeout=None):
        err = urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        err.read = lambda: b'{"error":"model \'qwen2.5vl:7b\' not found, try pulling it first"}'
        raise err

    monkeypatch.setattr("urllib.request.urlopen", _raise_with_body)
    with pytest.raises(VisionOcrUnavailable, match="ollama pull"):
        read_invoice_rows(image)


def test_read_invoice_rows_wraps_a_non_json_response_instead_of_crashing(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")

    class _PlainTextResponse:
        def read(self):
            return b"OK"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _PlainTextResponse())
    with pytest.raises(VisionOcrUnavailable, match="Ollama"):
        read_invoice_rows(image)


def test_read_invoice_rows_refuses_to_return_a_partial_table_when_cut_off(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"response": '{"rows": [{"name_ru": "x"', "done_reason": "length"}),
    )
    with pytest.raises(VisionOcrParseError, match="CHƯA ĐỌC HẾT"):
        read_invoice_rows(image)


def test_read_invoice_rows_refuses_to_return_rows_when_json_is_unparseable(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"response": "not json at all"}),
    )
    with pytest.raises(VisionOcrParseError):
        read_invoice_rows(image)


def test_read_invoice_rows_handles_a_response_wrapped_in_a_markdown_fence(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")
    wrapped = "```json\n" + json.dumps({"rows": [{"name_ru": "x", "name_latin": "y", "qty": 1, "unit": "шт", "unit_price": 1, "line_total": 1}]}) + "\n```"
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"response": wrapped}))
    rows = read_invoice_rows(image)
    assert len(rows) == 1
