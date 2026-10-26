import json
import time
import urllib.error

import pytest

from shop.core.customers import add_customer
from shop.core.invoices import get_invoice
from shop.core.pricing import unit_price as calc_unit_price
from shop.core.online_orders import (
    SyncError,
    batch_demand_by_code,
    batch_delivered_by_code,
    batch_excluded_codes,
    batch_linked_invoices,
    batch_shortage_report,
    close_batch,
    convert_to_invoice,
    link_customer,
    link_invoice_to_batch,
    linked_customer_id,
    list_batch_order_lines_for_code,
    list_online_orders,
    mark_cancelled,
    pending_demand_by_code,
    set_code_excluded,
    set_order_line_excluded,
    set_order_line_qty,
    sync_from_bot,
    unlink_invoice_from_batch,
)
from shop.core.products import upsert_product
from shop.core import supplier_invoices as supplier_invoices_core


def _seed_product(conn, code, cost, name=None):
    upsert_product(conn, code, name or code, "goi", cost, source="test")


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


def _sample_order(key, chat_id=111, code="BUN01", qty=2, name="Bún khô", price=161):
    return {
        "key": key,
        "telegram_chat_id": chat_id,
        "customer_label": "Khach (id 111)",
        "customer_phone": "+79990001122",
        "total_estimated": qty * price,
        "created_at": "2026-10-19T10:00:00Z",
        "lines": [{"code": code, "qty": qty, "name": name, "price": price}],
    }


def test_sync_from_bot_requires_settings(conn):
    with pytest.raises(SyncError):
        sync_from_bot(conn, "", "secret")
    with pytest.raises(SyncError):
        sync_from_bot(conn, "https://example.test", "")


def test_sync_from_bot_inserts_orders_and_lines(conn, monkeypatch):
    _seed_product(conn, "BUN01", cost=150, name="Bún khô")
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order("sync:0001-111-ab")]})
    )

    inserted = sync_from_bot(conn, "https://example.test", "secret")
    assert inserted == 1

    orders = list_online_orders(conn)
    assert len(orders) == 1
    assert orders[0]["customer_label"] == "Khach (id 111)"
    assert orders[0]["status"] == "cho_xu_ly"
    assert orders[0]["lines"] == [
        {
            "id": orders[0]["lines"][0]["id"],
            "code": "BUN01",
            "qty": 2,
            "name_at_order": "Bún khô",
            "price_at_order": 161,
            "excluded": False,
            "original_qty": None,
        }
    ]


def test_sync_from_bot_does_not_duplicate_an_already_synced_order(conn, monkeypatch):
    _seed_product(conn, "BUN01", cost=150)
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order("sync:0001-111-ab")]})
    )
    assert sync_from_bot(conn, "https://example.test", "secret") == 1
    # Same key comes back again (e.g. `since` wasn't honored server-side) --
    # source_key is UNIQUE, so this must not create a second row.
    assert sync_from_bot(conn, "https://example.test", "secret") == 0
    assert len(list_online_orders(conn)) == 1


def test_sync_from_bot_wraps_a_wrong_secret_in_a_vietnamese_message(conn, monkeypatch):
    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    with pytest.raises(SyncError, match="Mã đồng bộ"):
        sync_from_bot(conn, "https://example.test", "wrong-secret")


def test_sync_from_bot_wraps_a_network_failure_in_a_vietnamese_message(conn, monkeypatch):
    def _raise(req, timeout=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    with pytest.raises(SyncError, match="mạng"):
        sync_from_bot(conn, "https://example.test", "secret")


def test_sync_from_bot_wraps_a_non_json_response_instead_of_crashing(conn, monkeypatch):
    # A 200 response that isn't JSON (e.g. a VPN/captive-portal page) --
    # json.loads() raises ValueError, which must become a Vietnamese
    # SyncError, not escape raw into the Qt slot that calls this.
    class _PlainTextResponse:
        def read(self):
            return b"OK"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _PlainTextResponse())
    with pytest.raises(SyncError, match="mạng"):
        sync_from_bot(conn, "https://example.test", "secret")


def test_pending_demand_by_code_sums_only_orders_still_awaiting_action(conn, monkeypatch):
    _seed_product(conn, "BUN01", cost=150)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen(
            {
                "orders": [
                    _sample_order("sync:0001-1-aa", chat_id=1, qty=2),
                    _sample_order("sync:0002-2-bb", chat_id=2, qty=3),
                ]
            }
        ),
    )
    sync_from_bot(conn, "https://example.test", "secret")

    demand = pending_demand_by_code(conn)
    assert demand == [{"code": "BUN01", "total_qty": 5, "name": "Bún khô"}]

    # Cancel one -- it must drop out of demand.
    orders = list_online_orders(conn)
    mark_cancelled(conn, orders[0]["id"])
    demand_after = pending_demand_by_code(conn)
    assert demand_after[0]["total_qty"] == 3


def test_convert_to_invoice_prices_from_current_catalog_at_the_customers_own_markup(conn, monkeypatch):
    # The bot snapshotted 161 at order time; the real cost has since
    # changed, AND this customer has a non-default markup -- the
    # invoice line must reflect both, never the bot's stale snapshot
    # and never silently fall back to the public 7% default.
    _seed_product(conn, "BUN01", cost=200, name="Bún khô")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"orders": [_sample_order("sync:0001-111-ab", code="BUN01", qty=2, price=161)]}),
    )
    sync_from_bot(conn, "https://example.test", "secret")
    online_order_id = list_online_orders(conn)[0]["id"]

    customer_id = add_customer(conn, "Khach test", default_markup_pct=12)
    invoice_id, dropped, excluded = convert_to_invoice(conn, online_order_id, customer_id)

    assert dropped == []
    assert excluded == []
    invoice = get_invoice(conn, invoice_id)
    assert invoice["customer_id"] == customer_id
    assert len(invoice["lines"]) == 1
    assert invoice["lines"][0]["qty"] == 2
    assert invoice["lines"][0]["unit_price"] == calc_unit_price(200, 12)

    orders = list_online_orders(conn, status="da_tao_hoa_don")
    assert len(orders) == 1
    assert orders[0]["linked_invoice_id"] == invoice_id
    assert linked_customer_id(conn, "111") == customer_id


def test_convert_to_invoice_still_works_for_a_product_hidden_after_the_order_was_placed(conn, monkeypatch):
    # "Xóa khỏi danh mục" (25/10/2026) only sets active=0 -- it must NOT
    # behave like a dropped/missing code for an order placed while the
    # product was still active. get_product()/add_line() intentionally
    # have no active filter; this locks that in as a real invariant
    # instead of an accident nobody tests for.
    from shop.core.products import set_active

    _seed_product(conn, "RUOU01", cost=500, name="Rượu Tết 2026")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"orders": [_sample_order("sync:0001-111-ab", code="RUOU01", qty=1, price=535)]}),
    )
    sync_from_bot(conn, "https://example.test", "secret")
    online_order_id = list_online_orders(conn)[0]["id"]

    set_active(conn, "RUOU01", False)  # owner hides it once the sale window closes

    customer_id = add_customer(conn, "Khach test")
    invoice_id, dropped, excluded = convert_to_invoice(conn, online_order_id, customer_id)

    assert dropped == []
    assert excluded == []
    invoice = get_invoice(conn, invoice_id)
    assert len(invoice["lines"]) == 1
    assert invoice["lines"][0]["qty"] == 1


def test_convert_to_invoice_reports_a_code_no_longer_in_the_catalog_as_dropped(conn, monkeypatch):
    # A dropped code alongside a still-convertible one -- the dropped
    # one is reported but skipped, not fatal (unlike the all-dropped/
    # all-excluded case, see test_convert_to_invoice_refuses_an_order_with_nothing_left_to_bill).
    _seed_product(conn, "BUN01", cost=150)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen(
            {
                "orders": [
                    {
                        **_sample_order("sync:0001-111-ab", code="GONE01", qty=1),
                        "lines": [
                            {"code": "GONE01", "qty": 1, "name": "Hết hàng mẫu", "price": 100},
                            {"code": "BUN01", "qty": 2, "name": "Bún khô", "price": 161},
                        ],
                    }
                ]
            }
        ),
    )
    sync_from_bot(conn, "https://example.test", "secret")
    online_order_id = list_online_orders(conn)[0]["id"]
    customer_id = add_customer(conn, "Khach test")

    invoice_id, dropped, excluded = convert_to_invoice(conn, online_order_id, customer_id)

    assert dropped == ["GONE01"]
    assert excluded == []
    lines = get_invoice(conn, invoice_id)["lines"]
    assert len(lines) == 1
    assert lines[0]["product_code"] == "BUN01"


def test_convert_to_invoice_rejects_an_order_already_converted_or_cancelled(conn, monkeypatch):
    _seed_product(conn, "BUN01", cost=150)
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order("sync:0001-111-ab")]})
    )
    sync_from_bot(conn, "https://example.test", "secret")
    online_order_id = list_online_orders(conn)[0]["id"]
    customer_id = add_customer(conn, "Khach test")

    convert_to_invoice(conn, online_order_id, customer_id)
    with pytest.raises(ValueError):
        convert_to_invoice(conn, online_order_id, customer_id)


def test_sync_cursor_backs_off_so_a_late_propagating_older_key_is_not_permanently_skipped(conn, monkeypatch):
    # Cloudflare KV's list() is only eventually consistent (propagation
    # across edge locations can lag). If the next sync's `since` cursor
    # were the literal newest key ever seen, an order that was still
    # propagating when an even newer one had already landed would be
    # excluded by the Worker's `k.name > since` filter FOREVER, even
    # after it finishes propagating. The cursor this module sends must
    # therefore sit some margin BEHIND the newest key it has, not AT it.
    from shop.core.online_orders import _last_source_key, _SYNC_BACKOFF_MS

    _seed_product(conn, "BUN01", cost=150)
    newest_ts = 9_000_000_000_000
    newer_key = f"sync:{newest_ts:013d}-222-zz"
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"orders": [_sample_order(newer_key, chat_id=222)]}),
    )
    assert sync_from_bot(conn, "https://example.test", "secret") == 1

    cursor = _last_source_key(conn)
    assert cursor < newer_key
    cursor_ts = int(cursor.split(":", 1)[1])
    assert cursor_ts == newest_ts - _SYNC_BACKOFF_MS

    # An order from just inside that backoff window must compare as
    # "newer than the cursor" -- i.e. the Worker wouldn't have excluded it.
    older_key = f"sync:{newest_ts - _SYNC_BACKOFF_MS + 1000:013d}-111-aa"
    assert older_key > cursor


def test_reset_sync_floor_prevents_a_pre_reset_order_from_being_pulled_back_in(conn, monkeypatch):
    # A factory reset wipes online_orders (see shop.core.reset), but the
    # bot's KV still has the pre-reset order for up to 90 days -- the
    # Worker's OWN `since` filter is one defense, but this fake urlopen
    # deliberately ignores `since` (simulating the worst case) to prove
    # the floor written by set_sync_floor is a real, independent check,
    # not just trusting the server.
    from shop.core.reset import reset_transactional_data

    _seed_product(conn, "BUN01", cost=150)
    old_key = "sync:0000000000001-111-aa"
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order(old_key)]}))
    assert sync_from_bot(conn, "https://example.test", "secret") == 1

    reset_transactional_data(conn)
    assert list_online_orders(conn) == []

    # Same pre-reset order comes back from the bot again (e.g. the app
    # re-syncs from scratch since online_orders is now empty) -- must be
    # skipped, not silently re-inserted.
    assert sync_from_bot(conn, "https://example.test", "secret") == 0
    assert list_online_orders(conn) == []

    # A genuinely NEW order (placed after the reset) must still sync normally.
    new_key = f"sync:{int(time.time() * 1000) + 60_000:013d}-222-bb"
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order(new_key, chat_id=222)]}))
    assert sync_from_bot(conn, "https://example.test", "secret") == 1


def test_sync_floor_falls_back_to_the_legacy_meta_key_format(conn, monkeypatch):
    # The real database already had a floor written under the OLD key
    # ("sync_floor" -> "sync:<ms>") from a reset run before this module
    # renamed it to "sync_floor_ms" (lần 20) -- that floor must keep
    # protecting against pre-reset KV records reappearing, not silently
    # stop working the moment the code changed under it.
    from shop.core.online_orders import _sync_floor
    from shop.core.supplier_invoices import _photo_sync_floor

    legacy_ms = 1_792_483_485_612
    conn.execute("INSERT INTO shop_meta (key, value) VALUES ('sync_floor', ?)", (f"sync:{legacy_ms}",))
    conn.commit()

    assert _sync_floor(conn) == f"sync:{legacy_ms:013d}"
    assert _photo_sync_floor(conn) == f"photo:{legacy_ms:013d}"

    old_key = f"sync:{legacy_ms - 1000:013d}-111-aa"
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order(old_key)]}))
    assert sync_from_bot(conn, "https://example.test", "secret") == 0


def test_close_batch_groups_pending_unbatched_orders_and_leaves_later_ones_unbatched(conn, monkeypatch):
    _seed_product(conn, "BUN01", cost=150)
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order("sync:0001-111-ab", chat_id=111)]})
    )
    sync_from_bot(conn, "https://example.test", "secret")

    batch_id = close_batch(conn)
    first_order = list_online_orders(conn)[0]
    assert first_order["batch_id"] == batch_id

    # An order synced AFTER the close -- even though its own placed_at
    # could be earlier -- must stay unbatched, waiting for the NEXT
    # "Chốt đợt hàng mới" (documented edge case, see close_batch's
    # docstring), not retroactively join the already-closed batch.
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order("sync:0002-222-cd", chat_id=222)]})
    )
    sync_from_bot(conn, "https://example.test", "secret")
    orders_by_chat = {o["telegram_chat_id"]: o for o in list_online_orders(conn)}
    assert orders_by_chat["222"]["batch_id"] is None

    # Closing again only picks up the still-unbatched one.
    second_batch_id = close_batch(conn)
    assert second_batch_id != batch_id
    orders_by_chat = {o["telegram_chat_id"]: o for o in list_online_orders(conn)}
    assert orders_by_chat["222"]["batch_id"] == second_batch_id
    assert orders_by_chat["111"]["batch_id"] == batch_id  # unchanged


def test_set_code_excluded_strikes_it_from_every_pending_order_in_the_batch(conn, monkeypatch):
    _seed_product(conn, "BUN01", cost=150)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen(
            {
                "orders": [
                    _sample_order("sync:0001-1-aa", chat_id=1, qty=2, price=161),
                    _sample_order("sync:0002-2-bb", chat_id=2, qty=3, price=161),
                ]
            }
        ),
    )
    sync_from_bot(conn, "https://example.test", "secret")
    batch_id = close_batch(conn)

    assert batch_demand_by_code(conn, batch_id) == [{"code": "BUN01", "total_qty": 5, "name": "Bún khô", "order_count": 2}]
    assert batch_excluded_codes(conn, batch_id) == []

    affected = set_code_excluded(conn, batch_id, "BUN01", excluded=True)
    assert set(affected) == {o["id"] for o in list_online_orders(conn)}

    # Dropped out of demand (nothing left to restock this round)...
    assert batch_demand_by_code(conn, batch_id) == []
    # ...but still visible as excluded, with a record of who was affected.
    assert batch_excluded_codes(conn, batch_id) == [{"code": "BUN01", "name": "Bún khô", "order_count": 2}]
    # ...and each order's estimated total dropped to 0, not left stale.
    for order in list_online_orders(conn):
        assert order["total_estimated"] == 0

    # Reversible on a misclick.
    set_code_excluded(conn, batch_id, "BUN01", excluded=False)
    assert batch_demand_by_code(conn, batch_id) == [{"code": "BUN01", "total_qty": 5, "name": "Bún khô", "order_count": 2}]
    assert batch_excluded_codes(conn, batch_id) == []


def test_convert_to_invoice_skips_an_excluded_line_and_reports_it_separately_from_dropped(conn, monkeypatch):
    _seed_product(conn, "BUN01", cost=150)
    _seed_product(conn, "GAO001", cost=200, name="Gạo")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen(
            {
                "orders": [
                    {
                        **_sample_order("sync:0001-111-ab", code="BUN01", qty=2, price=161),
                        "lines": [
                            {"code": "BUN01", "qty": 2, "name": "Bún khô", "price": 161},
                            {"code": "GAO001", "qty": 1, "name": "Gạo", "price": 300},
                        ],
                    }
                ]
            }
        ),
    )
    sync_from_bot(conn, "https://example.test", "secret")
    batch_id = close_batch(conn)
    set_code_excluded(conn, batch_id, "GAO001", excluded=True)

    online_order_id = list_online_orders(conn)[0]["id"]
    customer_id = add_customer(conn, "Khach test")
    invoice_id, dropped, excluded = convert_to_invoice(conn, online_order_id, customer_id)

    assert dropped == []
    assert excluded == ["GAO001"]
    lines = get_invoice(conn, invoice_id)["lines"]
    assert len(lines) == 1
    assert lines[0]["product_code"] == "BUN01"


def test_convert_to_invoice_refuses_an_order_with_nothing_left_to_bill(conn, monkeypatch):
    # Every line excluded (request #1: the only item in this order is
    # what the supplier didn't have) -- must NOT create an empty draft
    # invoice, because online_orders.linked_invoice_id would then point
    # at it with no cascade, and delete_draft_invoice would hit a
    # FOREIGN KEY failure trying to remove that empty draft.
    _seed_product(conn, "BUN01", cost=150)
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order("sync:0001-111-ab", code="BUN01", qty=1)]})
    )
    sync_from_bot(conn, "https://example.test", "secret")
    batch_id = close_batch(conn)
    set_code_excluded(conn, batch_id, "BUN01", excluded=True)

    online_order_id = list_online_orders(conn)[0]["id"]
    customer_id = add_customer(conn, "Khach test")
    with pytest.raises(ValueError, match="Hủy đơn"):
        convert_to_invoice(conn, online_order_id, customer_id)

    # The order must still be convertible/cancellable afterwards -- not
    # left half-processed by the failed attempt.
    assert list_online_orders(conn)[0]["status"] == "cho_xu_ly"


def test_pending_demand_by_code_excludes_orders_already_in_a_batch(conn, monkeypatch):
    # Request #2: "Cần nhập hàng gì?" previews what's NOT yet chốt --
    # mixing it with an already-closed batch's demand (which "Duyệt đợt
    # hàng…" owns, pruned of unavailable items) would give the owner one
    # misleading combined number to actually order from the supplier.
    _seed_product(conn, "BUN01", cost=150)
    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order("sync:0001-1-aa", chat_id=1, qty=2)]})
    )
    sync_from_bot(conn, "https://example.test", "secret")
    close_batch(conn)  # this order is now in a batch

    monkeypatch.setattr(
        "urllib.request.urlopen", _fake_urlopen({"orders": [_sample_order("sync:0002-2-bb", chat_id=2, qty=3)]})
    )
    sync_from_bot(conn, "https://example.test", "secret")  # this one is NOT yet batched

    assert pending_demand_by_code(conn) == [{"code": "BUN01", "total_qty": 3, "name": "Bún khô"}]


def test_link_customer_upserts_instead_of_erroring_on_a_second_call(conn):
    c1 = add_customer(conn, "A")
    c2 = add_customer(conn, "B")
    link_customer(conn, "555", c1)
    assert linked_customer_id(conn, "555") == c1
    link_customer(conn, "555", c2)
    assert linked_customer_id(conn, "555") == c2


def _seed_batch_with_two_customers(conn, monkeypatch, qty1=2, qty2=3):
    """2 customers, each with 1 line of BUN01, closed into 1 batch --
    the shared setup for the invoice-linking/shortage tests below."""
    _seed_product(conn, "BUN01", cost=150, name="Bún khô")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen(
            {
                "orders": [
                    _sample_order("sync:0001-111-aa", chat_id=111, qty=qty1),
                    _sample_order("sync:0002-222-bb", chat_id=222, qty=qty2),
                ]
            }
        ),
    )
    sync_from_bot(conn, "https://example.test", "secret")
    return close_batch(conn)


def test_link_invoice_to_batch_then_batch_linked_invoices_lists_it(conn, monkeypatch):
    batch_id = _seed_batch_with_two_customers(conn, monkeypatch)
    inv_id = supplier_invoices_core.create_invoice(conn, invoice_number="UT-1")

    link_invoice_to_batch(conn, inv_id, batch_id)

    linked = batch_linked_invoices(conn, batch_id)
    assert len(linked) == 1
    assert linked[0]["id"] == inv_id

    unlink_invoice_from_batch(conn, inv_id)
    assert batch_linked_invoices(conn, batch_id) == []


def test_link_invoice_to_batch_rejects_unknown_ids(conn, monkeypatch):
    batch_id = _seed_batch_with_two_customers(conn, monkeypatch)
    inv_id = supplier_invoices_core.create_invoice(conn)
    with pytest.raises(ValueError):
        link_invoice_to_batch(conn, inv_id, batch_id=99999)
    with pytest.raises(ValueError):
        link_invoice_to_batch(conn, supplier_invoice_id=99999, batch_id=batch_id)


def test_batch_delivered_by_code_sums_across_every_linked_invoice_with_unit_conversion(conn, monkeypatch):
    batch_id = _seed_batch_with_two_customers(conn, monkeypatch, qty1=2, qty2=3)  # 5 ordered total
    inv1 = supplier_invoices_core.create_invoice(conn)
    supplier_invoices_core.add_line(conn, inv1, "Bun kho", 1, "кор (30 шт)", 1590, matched_code="BUN01", unit_conversion=30)
    inv2 = supplier_invoices_core.create_invoice(conn)
    supplier_invoices_core.add_line(conn, inv2, "Bun kho them", 10, "шт", 150, matched_code="BUN01", unit_conversion=1)
    link_invoice_to_batch(conn, inv1, batch_id)
    link_invoice_to_batch(conn, inv2, batch_id)

    delivered, incomplete = batch_delivered_by_code(conn, batch_id)

    assert delivered == {"BUN01": 40.0}  # 1*30 + 10*1
    assert incomplete == 0


def test_batch_delivered_by_code_counts_unmatched_or_unquantified_lines_as_incomplete(conn, monkeypatch):
    batch_id = _seed_batch_with_two_customers(conn, monkeypatch)
    inv = supplier_invoices_core.create_invoice(conn)
    supplier_invoices_core.add_line(conn, inv, "chua khop ten", 5, "шт", 100, matched_code=None)
    supplier_invoices_core.add_line(conn, inv, "da khop nhung chua go SL", None, "шт", 100, matched_code="BUN01")
    link_invoice_to_batch(conn, inv, batch_id)

    delivered, incomplete = batch_delivered_by_code(conn, batch_id)

    assert delivered == {}  # neither line contributes
    assert incomplete == 2


def test_batch_shortage_report_flags_shortage_but_not_an_exact_match(conn, monkeypatch):
    _seed_product(conn, "MAM004", cost=350, name="Nước mắm Chinsu")
    _seed_product(conn, "BUN01", cost=150, name="Bún khô")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen(
            {
                "orders": [
                    _sample_order("sync:0001-111-aa", chat_id=111, code="BUN01", qty=5, price=150),
                    _sample_order("sync:0002-222-bb", chat_id=222, code="MAM004", qty=4, name="Nước mắm Chinsu", price=350),
                ]
            }
        ),
    )
    sync_from_bot(conn, "https://example.test", "secret")
    batch_id = close_batch(conn)

    inv = supplier_invoices_core.create_invoice(conn)
    supplier_invoices_core.add_line(conn, inv, "Bun kho", 3, "шт", 150, matched_code="BUN01", unit_conversion=1)  # 3 delivered, 5 ordered -> short 2
    supplier_invoices_core.add_line(conn, inv, "Mam Chinsu", 4, "шт", 350, matched_code="MAM004", unit_conversion=1)  # exact match
    link_invoice_to_batch(conn, inv, batch_id)

    report = {r["code"]: r for r in batch_shortage_report(conn, batch_id)}
    assert "MAM004" not in report  # exact match, nothing to review
    assert report["BUN01"]["ordered"] == 5
    assert report["BUN01"]["delivered"] == 3
    assert report["BUN01"]["diff"] == 2  # shortage


def test_list_batch_order_lines_for_code_returns_one_row_per_customer(conn, monkeypatch):
    batch_id = _seed_batch_with_two_customers(conn, monkeypatch, qty1=2, qty2=3)
    rows = list_batch_order_lines_for_code(conn, batch_id, "BUN01")
    assert len(rows) == 2
    assert {r["qty"] for r in rows} == {2, 3}
    assert all(r["excluded"] is False for r in rows)


def test_set_order_line_qty_adjusts_only_that_line_and_recomputes_its_orders_total(conn, monkeypatch):
    batch_id = _seed_batch_with_two_customers(conn, monkeypatch, qty1=2, qty2=3)
    rows = list_batch_order_lines_for_code(conn, batch_id, "BUN01")
    target = rows[0]

    set_order_line_qty(conn, target["line_id"], 1)  # the supplier only had 1 left for this customer

    updated = list_batch_order_lines_for_code(conn, batch_id, "BUN01")
    qtys = sorted(r["qty"] for r in updated)
    assert qtys == [1, rows[1]["qty"]]  # only the targeted line changed
    order = [o for o in list_online_orders(conn) if o["id"] == target["online_order_id"]][0]
    assert order["total_estimated"] == 1 * 161  # BUN01's price_at_order from _sample_order's default


def test_set_order_line_qty_rejects_zero_or_negative(conn, monkeypatch):
    batch_id = _seed_batch_with_two_customers(conn, monkeypatch)
    line_id = list_batch_order_lines_for_code(conn, batch_id, "BUN01")[0]["line_id"]
    with pytest.raises(ValueError):
        set_order_line_qty(conn, line_id, 0)
    with pytest.raises(ValueError):
        set_order_line_qty(conn, line_id, -1)


def test_set_order_line_excluded_only_affects_the_one_line_not_the_whole_code(conn, monkeypatch):
    batch_id = _seed_batch_with_two_customers(conn, monkeypatch, qty1=2, qty2=3)
    rows = list_batch_order_lines_for_code(conn, batch_id, "BUN01")
    target = rows[0]

    set_order_line_excluded(conn, target["line_id"], True)

    updated = {r["line_id"]: r for r in list_batch_order_lines_for_code(conn, batch_id, "BUN01")}
    assert updated[target["line_id"]]["excluded"] is True
    other_id = rows[1]["line_id"]
    assert updated[other_id]["excluded"] is False  # unaffected, unlike set_code_excluded
    order = [o for o in list_online_orders(conn) if o["id"] == target["online_order_id"]][0]
    assert order["total_estimated"] == 0  # its only line is now excluded
