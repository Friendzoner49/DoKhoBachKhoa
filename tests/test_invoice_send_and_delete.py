"""Sending a finalized invoice to the customer on Telegram, and deleting a
supplier invoice. Fake data only (public repo)."""
import json

import pytest

import shop.core.supplier_invoices as si
from shop.core import invoices as inv
from shop.core.customers import add_customer
from shop.core.invoice_send import InvoiceSendError, build_invoice_message, send_invoice_to_customer
from shop.core.products import upsert_product


def _finalized_invoice(conn):
    upsert_product(conn, "TST01", "Hàng thử", "gói", 100, source="t")
    customer = add_customer(conn, "Khách thử", default_markup_pct=10)
    invoice_id = inv.create_invoice(conn, customer)
    inv.add_line(conn, invoice_id, "TST01", qty=3, markup_pct=10)
    inv.finalize_invoice(conn, invoice_id)
    return customer, invoice_id


def test_message_lists_lines_total_and_debt(conn, monkeypatch):
    monkeypatch.setattr("shop.core.invoice_send.payment_info", lambda: "+70000000000\nBank A/Bank B")
    _customer, invoice_id = _finalized_invoice(conn)
    text = build_invoice_message(conn, invoice_id)
    assert "Hóa đơn #" in text and "Hàng thử: 3 × 110 = 330 ₽" in text
    assert "Tổng: 330 ₽" in text and "Công nợ hiện tại: 330 ₽" in text
    # transfer details sit near the end, right before the thanks
    assert text.rstrip().endswith("💳 Chuyển khoản:\n+70000000000\nBank A/Bank B\n\nXin cảm ơn quý khách!")


def test_message_without_payment_info_just_ends_with_thanks(conn, monkeypatch):
    monkeypatch.setattr("shop.core.invoice_send.payment_info", lambda: "")
    _customer, invoice_id = _finalized_invoice(conn)
    text = build_invoice_message(conn, invoice_id)
    assert "Chuyển khoản" not in text and text.rstrip().endswith("Xin cảm ơn quý khách!")


def test_send_needs_finalized_invoice_and_a_linked_chat(conn, monkeypatch):
    customer, invoice_id = _finalized_invoice(conn)
    with pytest.raises(InvoiceSendError, match="chưa liên kết Telegram"):
        send_invoice_to_customer(conn, invoice_id, "https://w.test", "secret")

    conn.execute("INSERT INTO telegram_customer_links (telegram_chat_id, customer_id) VALUES ('555', ?)", (customer,))
    draft = inv.create_invoice(conn, customer)
    inv.add_line(conn, draft, "TST01", qty=1, markup_pct=10)
    with pytest.raises(InvoiceSendError, match="HOÀN TẤT"):
        send_invoice_to_customer(conn, draft, "https://w.test", "secret")

    sent = []

    def fake_request(url, secret, path, body=None, timeout=60.0):
        sent.append((path, body))
        return json.dumps({"results": [{"chat_id": "555", "ok": True}]}).encode()

    monkeypatch.setattr("shop.core.invoice_send._worker_request", fake_request)
    assert send_invoice_to_customer(conn, invoice_id, "https://w.test", "secret") == 1
    (path, body), = sent
    assert path == "/notify/arrival" and body["messages"][0]["chat_id"] == "555"  # only THIS customer's chat
    assert conn.execute("SELECT telegram_sent_at FROM invoices WHERE id = ?", (invoice_id,)).fetchone()[0]


def test_failed_send_is_not_marked_sent(conn, monkeypatch):
    customer, invoice_id = _finalized_invoice(conn)
    conn.execute("INSERT INTO telegram_customer_links (telegram_chat_id, customer_id) VALUES ('555', ?)", (customer,))
    monkeypatch.setattr(
        "shop.core.invoice_send._worker_request",
        lambda *a, **k: json.dumps({"results": [{"chat_id": "555", "ok": False, "error": "blocked"}]}).encode(),
    )
    with pytest.raises(InvoiceSendError, match="blocked"):
        send_invoice_to_customer(conn, invoice_id, "https://w.test", "secret")
    assert conn.execute("SELECT telegram_sent_at FROM invoices WHERE id = ?", (invoice_id,)).fetchone()[0] is None


def test_delete_supplier_invoice_removes_rows_and_stops_telegram_resync(conn, tmp_path, monkeypatch):
    upsert_product(conn, "TST01", "Hàng thử", "gói", 100, source="t")
    key = "photo:0001761000900000-abc"
    invoice_id = si.create_invoice(conn, source_key=key)
    si.add_line(conn, invoice_id, "x", 1, "шт", 100, matched_code="TST01")
    batch = conn.execute("INSERT INTO order_batches (closed_at, supplier_invoice_id) VALUES ('2026-11-06', ?)", (invoice_id,)).lastrowid

    si.delete_supplier_invoice(conn, invoice_id)
    assert conn.execute("SELECT COUNT(*) FROM supplier_invoices").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM supplier_invoice_lines").fetchone()[0] == 0
    assert conn.execute("SELECT supplier_invoice_id FROM order_batches WHERE id = ?", (batch,)).fetchone()[0] is None

    # the same photo still sitting on the Worker must not come back
    monkeypatch.setattr(si, "fetch_sync_json", lambda *a, **k: {"photos": [{"key": key, "note": "again"}]})
    assert si.sync_photos_from_bot(conn, "https://w.test", "secret", tmp_path) == 0
