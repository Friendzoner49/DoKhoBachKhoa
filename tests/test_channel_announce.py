import base64
import json
import urllib.error

import pytest

from shop.core.channel_announce import AnnounceError, announce_product, build_caption
from shop.core.products import get_product, set_sale_until, upsert_product


class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(payload=None, capture: list | None = None):
    def _open(req, timeout=None):
        if capture is not None:
            capture.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse(payload or {"ok": True})

    return _open


def _seed_with_image(conn, tmp_path, code="RUOU01", filename="RUOU01.jpg", cost=1000):
    upsert_product(conn, code, "Rượu Vodka", "chai", cost, source="test")
    from shop.core.products import set_image_filename

    set_image_filename(conn, code, filename)
    (tmp_path / filename).write_bytes(b"fake-jpeg-bytes")
    return code


def test_announce_product_requires_settings(conn, tmp_path):
    code = _seed_with_image(conn, tmp_path)
    with pytest.raises(AnnounceError):
        announce_product(conn, code, "", "secret", tmp_path)
    with pytest.raises(AnnounceError):
        announce_product(conn, code, "https://example.test", "", tmp_path)


def test_announce_product_requires_an_image(conn, tmp_path):
    upsert_product(conn, "RUOU02", "Rượu Soju", "chai", 500, source="test")
    with pytest.raises(AnnounceError):
        announce_product(conn, "RUOU02", "https://example.test", "secret", tmp_path)


def test_announce_product_requires_the_image_file_to_actually_exist(conn, tmp_path):
    from shop.core.products import set_image_filename

    upsert_product(conn, "RUOU03", "Rượu Soju", "chai", 500, source="test")
    set_image_filename(conn, "RUOU03", "missing.jpg")
    with pytest.raises(AnnounceError):
        announce_product(conn, "RUOU03", "https://example.test", "secret", tmp_path)


def test_announce_product_sends_the_caption_and_public_image_url_then_marks_announced(conn, monkeypatch, tmp_path):
    code = _seed_with_image(conn, tmp_path)
    set_sale_until(conn, code, "2026-11-01")
    captured = []
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(capture=captured))

    announce_product(conn, code, "https://example.test", "secret", tmp_path)

    assert len(captured) == 1
    body = captured[0]
    assert body["code"] == code
    assert body["filename"] == "RUOU01.jpg"
    assert base64.b64decode(body["imageBase64"]) == b"fake-jpeg-bytes"
    assert "01/11/2026" in body["caption"]

    product = get_product(conn, code)
    assert product["channel_announced_at"] is not None


def test_build_caption_includes_name_price_and_sale_window(conn, tmp_path):
    code = _seed_with_image(conn, tmp_path, cost=1000)
    set_sale_until(conn, code, "2026-11-05")
    product = get_product(conn, code)
    caption = build_caption(product)
    assert "Rượu Vodka" in caption
    assert "05/11/2026" in caption
    assert "friendzoner49.github.io" in caption


def test_announce_product_wraps_a_wrong_secret_in_a_vietnamese_message(conn, monkeypatch, tmp_path):
    code = _seed_with_image(conn, tmp_path)

    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    with pytest.raises(AnnounceError):
        announce_product(conn, code, "https://example.test", "wrong-secret", tmp_path)


def test_announce_product_wraps_a_failed_photo_send_in_a_vietnamese_message(conn, monkeypatch, tmp_path):
    code = _seed_with_image(conn, tmp_path)

    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    with pytest.raises(AnnounceError, match="CHANNEL_CHAT_ID"):
        announce_product(conn, code, "https://example.test", "secret", tmp_path)


def test_announce_product_warns_a_timeout_may_already_have_posted(conn, monkeypatch, tmp_path):
    code = _seed_with_image(conn, tmp_path)

    def _raise(req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    with pytest.raises(AnnounceError, match="CÓ THỂ TIN ĐÃ ĐĂNG"):
        announce_product(conn, code, "https://example.test", "secret", tmp_path)


def test_announce_product_wraps_a_non_json_response_instead_of_crashing(conn, monkeypatch, tmp_path):
    code = _seed_with_image(conn, tmp_path)

    class _PlainTextResponse:
        def read(self):
            return b"OK"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _PlainTextResponse())
    with pytest.raises(AnnounceError):
        announce_product(conn, code, "https://example.test", "secret", tmp_path)
