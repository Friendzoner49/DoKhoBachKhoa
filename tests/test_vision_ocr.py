import json
import urllib.error

import pytest

from shop.ocr.vision import VisionOcrUnavailable, read_invoice_table


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


def test_read_invoice_table_returns_the_model_response(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"not a real image, just needs to exist")
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"response": "1. Nuoc mam CHINSU 250ml, 2, chai, 150.00, 300.00"})
    )
    text = read_invoice_table(image)
    assert "Nuoc mam" in text


def test_read_invoice_table_wraps_connection_refused_in_a_vietnamese_message(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")

    def _raise(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    with pytest.raises(VisionOcrUnavailable, match="Ollama"):
        read_invoice_table(image)


def test_read_invoice_table_wraps_a_missing_model_in_a_vietnamese_message(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")

    def _raise_with_body(req, timeout=None):
        err = urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        err.read = lambda: b'{"error":"model \'qwen2.5vl:7b\' not found, try pulling it first"}'
        raise err

    monkeypatch.setattr("urllib.request.urlopen", _raise_with_body)
    with pytest.raises(VisionOcrUnavailable, match="ollama pull"):
        read_invoice_table(image)


def test_read_invoice_table_wraps_a_non_json_response_instead_of_crashing(tmp_path, monkeypatch):
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
        read_invoice_table(image)


def test_read_invoice_table_warns_when_the_model_was_cut_off(tmp_path, monkeypatch):
    image = tmp_path / "invoice.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"response": "1. Nuoc mam CHINSU...", "done_reason": "length"}),
    )
    text = read_invoice_table(image)
    assert "CHƯA ĐỌC HẾT" in text


