import json
import urllib.error

import pytest

from shop.core.arrival_notify import (
    NotifyError,
    build_customer_message,
    prepare_arrival_messages,
    send_arrival_notifications,
)
from shop.core.online_orders import close_batch, list_online_orders, sync_from_bot
from shop.core.products import upsert_product


class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(payload, capture: list | None = None):
    def _open(req, timeout=None):
        if capture is not None:
            capture.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse(payload)

    return _open


def _sample_order(key, chat_id, code="BUN01", qty=2, name="Bún khô", price=161):
    return {
        "key": key,
        "telegram_chat_id": chat_id,
        "customer_label": f"Khach (id {chat_id})",
        "customer_phone": "+79990001122",
        "total_estimated": qty * price,
        "created_at": "2026-10-25T10:00:00Z",
        "lines": [{"code": code, "qty": qty, "name": name, "price": price}],
    }


def _seed_batch(conn, monkeypatch):
    upsert_product(conn, "BUN01", "Bún khô", "gói", 150, source="test")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"orders": [_sample_order("sync:0001-111-aa", chat_id=111)]}),
    )
    sync_from_bot(conn, "https://example.test", "secret")
    return close_batch(conn)


# ---- build_customer_message: pure function ----


def test_build_customer_message_lists_each_delivered_line_with_no_total():
    lines = [{"name_at_order": "Bún khô", "qty": 2, "original_qty": None, "excluded": False}]
    text = build_customer_message(lines)
    assert "Bún khô: 2" in text
    assert "₽" not in text and "RUB" not in text  # no money total


def test_build_customer_message_notes_a_reduced_quantity():
    lines = [{"name_at_order": "Bún khô", "qty": 1, "original_qty": 3, "excluded": False}]
    text = build_customer_message(lines)
    assert "Bún khô: 1 (đặt 3)" in text


def test_build_customer_message_marks_an_excluded_line_as_missing():
    lines = [
        {"name_at_order": "Bún khô", "qty": 2, "original_qty": None, "excluded": False},
        {"name_at_order": "Mắm tôm", "qty": 1, "original_qty": None, "excluded": True},
    ]
    text = build_customer_message(lines)
    assert "Mắm tôm: đợt này không có" in text
    assert "Bún khô: 2" in text


def test_build_customer_message_still_sends_something_when_the_whole_order_was_excluded():
    lines = [{"name_at_order": "Bún khô", "qty": 2, "original_qty": None, "excluded": True}]
    text = build_customer_message(lines)
    assert text  # never empty/silent
    assert "không có" in text


# ---- prepare_arrival_messages ----


def test_prepare_arrival_messages_skips_orders_already_notified(conn, monkeypatch):
    batch_id = _seed_batch(conn, monkeypatch)
    assert len(prepare_arrival_messages(conn, batch_id)) == 1

    order_id = list_online_orders(conn)[0]["id"]
    conn.execute("UPDATE online_orders SET arrival_notified_at = '2026-10-25T10:00:00Z' WHERE id = ?", (order_id,))
    conn.commit()

    assert prepare_arrival_messages(conn, batch_id) == []


# ---- send_arrival_notifications ----


def test_send_arrival_notifications_requires_settings(conn):
    with pytest.raises(NotifyError):
        send_arrival_notifications(conn, batch_id=1, worker_url="", sync_secret="secret")


def test_send_arrival_notifications_marks_only_confirmed_chats_as_notified(conn, monkeypatch):
    batch_id = _seed_batch(conn, monkeypatch)
    order = list_online_orders(conn)[0]
    captured = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"results": [{"chat_id": "111", "ok": True}]}, capture=captured),
    )

    result = send_arrival_notifications(conn, batch_id, "https://example.test", "secret")

    assert len(result["sent"]) == 1
    assert result["failed"] == []
    refreshed = [o for o in list_online_orders(conn) if o["id"] == order["id"]][0]
    assert refreshed["arrival_notified_at"] is not None
    assert captured[0]["messages"][0]["chat_id"] == "111"
    assert "₽" not in captured[0]["messages"][0]["text"]


def test_send_arrival_notifications_does_not_mark_a_chat_the_worker_reports_failed(conn, monkeypatch):
    batch_id = _seed_batch(conn, monkeypatch)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"results": [{"chat_id": "111", "ok": False, "error": "bot was blocked by the user"}]}),
    )

    result = send_arrival_notifications(conn, batch_id, "https://example.test", "secret")

    assert result["sent"] == []
    assert len(result["failed"]) == 1
    assert result["failed"][0]["error"] == "bot was blocked by the user"
    refreshed = list_online_orders(conn)[0]
    assert refreshed["arrival_notified_at"] is None  # not marked -- stays retryable


def test_send_arrival_notifications_treats_a_non_json_reply_as_undeployed_worker(conn, monkeypatch):
    # The exact lần 20 bug: an undeployed Worker's catch-all answers
    # unknown paths with 200 "OK" (plain text) -- this must NOT be read
    # as "every DM sent".
    batch_id = _seed_batch(conn, monkeypatch)

    class _PlainTextResponse:
        def read(self):
            return b"OK"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _PlainTextResponse())

    with pytest.raises(NotifyError, match="deploy lại Worker"):
        send_arrival_notifications(conn, batch_id, "https://example.test", "secret")

    refreshed = list_online_orders(conn)[0]
    assert refreshed["arrival_notified_at"] is None  # nothing marked sent on this failure


def test_send_arrival_notifications_is_safe_to_retry_after_a_partial_failure(conn, monkeypatch):
    batch_id = _seed_batch(conn, monkeypatch)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"results": [{"chat_id": "111", "ok": False, "error": "timeout"}]}),
    )
    send_arrival_notifications(conn, batch_id, "https://example.test", "secret")

    # Retry: this time the Worker confirms it.
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"results": [{"chat_id": "111", "ok": True}]}),
    )
    result = send_arrival_notifications(conn, batch_id, "https://example.test", "secret")

    assert len(result["sent"]) == 1
    refreshed = list_online_orders(conn)[0]
    assert refreshed["arrival_notified_at"] is not None


def test_send_arrival_notifications_does_nothing_when_nothing_pending(conn, monkeypatch):
    batch_id = _seed_batch(conn, monkeypatch)
    order_id = list_online_orders(conn)[0]["id"]
    conn.execute("UPDATE online_orders SET arrival_notified_at = '2026-10-25T10:00:00Z' WHERE id = ?", (order_id,))
    conn.commit()

    def _should_not_be_called(req, timeout=None):
        raise AssertionError("should not call the network when there's nothing to send")

    monkeypatch.setattr("urllib.request.urlopen", _should_not_be_called)

    result = send_arrival_notifications(conn, batch_id, "https://example.test", "secret")
    assert result == {"sent": [], "failed": []}
