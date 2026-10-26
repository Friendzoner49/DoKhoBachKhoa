import base64
import json
import sqlite3
import urllib.error

import pytest

from shop.core.products import get_product, upsert_product
from shop.core.supplier_invoices import (
    SyncError,
    add_line,
    apply_invoice,
    create_invoice,
    get_alias,
    get_invoice,
    known_lines,
    line_cost_preview,
    list_invoices,
    list_lines,
    save_alias,
    suggest_matches,
    sync_photos_from_bot,
    total_unpaid,
    update_line,
)


def _seed_product(conn, code, cost, name="Test product", unit="goi"):
    upsert_product(conn, code, name, unit, cost, source="test")


def test_line_cost_preview_normalizes_by_unit_conversion(conn):
    # Mirrors the real invoice's row 10: a case of 30 at 1590 RUB is 53/piece,
    # not 1590/piece -- comparing raw_unit_price to cost_price directly would
    # report a wildly wrong "price increase".
    _seed_product(conn, "MT0003", cost=53)
    inv = create_invoice(conn, invoice_number="UT-TEST")
    line_id = add_line(
        conn, inv, raw_name="Lau Thai acecook 80gr (1kor30shit)", raw_qty=1, raw_unit="кор (30 шт)",
        raw_unit_price=1590, matched_code="MT0003", unit_conversion=30,
    )
    line = list_lines(conn, inv)[0]
    assert line["id"] == line_id
    preview = line_cost_preview(conn, line)
    assert preview["old_cost"] == 53
    assert preview["new_cost"] == 53  # 1590 / 30 == 53, i.e. unchanged once normalized
    assert preview["delta_pct"] == 0


def test_line_cost_preview_flags_a_real_increase(conn):
    _seed_product(conn, "BOCA01", cost=40)
    inv = create_invoice(conn)
    add_line(conn, inv, raw_name="Sol so speciyami Hai chau 190g", raw_qty=3, raw_unit="шт", raw_unit_price=42, matched_code="BOCA01")
    line = list_lines(conn, inv)[0]
    preview = line_cost_preview(conn, line)
    assert preview["old_cost"] == 40
    assert preview["new_cost"] == 42
    assert round(preview["delta_pct"], 2) == 5.0


def test_unmatched_line_has_no_preview_and_is_skipped_on_apply(conn):
    inv = create_invoice(conn)
    add_line(conn, inv, raw_name="Mot mat hang la, chua tung thay", raw_qty=1, raw_unit="шт", raw_unit_price=999)
    line = list_lines(conn, inv)[0]
    assert line_cost_preview(conn, line) == {"old_cost": None, "new_cost": None, "delta_pct": None}

    applied = apply_invoice(conn, inv)
    assert applied == []


def test_apply_invoice_updates_cost_and_remembers_alias(conn):
    _seed_product(conn, "BOBC01", cost=185)
    inv = create_invoice(conn, invoice_number="UT-TEST-2")
    add_line(conn, inv, raw_name="Mua Banh Cuon 400g", raw_qty=1, raw_unit="шт", raw_unit_price=200, matched_code="BOBC01")

    applied = apply_invoice(conn, inv)
    assert len(applied) == 1
    assert get_product(conn, "BOBC01")["cost_price"] == 200

    alias = get_alias(conn, "Mua Banh Cuon 400g")
    assert alias == {"code": "BOBC01", "unit_conversion": 1.0}


def test_applying_twice_is_safe_and_only_reapplies_real_changes(conn):
    _seed_product(conn, "BONA01", cost=200)
    inv = create_invoice(conn)
    line_id = add_line(conn, inv, raw_name="Bot Nang 400g", raw_qty=2, raw_unit="шт", raw_unit_price=200, matched_code="BONA01")

    first = apply_invoice(conn, inv)
    assert len(first) == 1  # cost actually changed from nothing-recorded... still counts as an apply

    second = apply_invoice(conn, inv)
    assert len(second) == 1  # re-running still (harmlessly) re-applies the same unchanged cost
    assert get_product(conn, "BONA01")["cost_price"] == 200

    update_line(conn, line_id, raw_unit_price=250)
    third = apply_invoice(conn, inv)
    assert third[0]["old_cost"] == 200
    assert third[0]["new_cost"] == 250
    assert get_product(conn, "BONA01")["cost_price"] == 250


def test_suggest_matches_prefers_a_saved_alias_over_fresh_scoring(conn):
    _seed_product(conn, "BONV01", cost=20, name="Bột Ngũ Vị Hương")
    _seed_product(conn, "BONV02", cost=25, name="Bột Ngũ Vị Hương Cao Cấp")  # shares even more words
    save_alias(conn, "Bot Ngu vi Huong xanh", "BONV01", 1.0)

    matches = suggest_matches(conn, "Bot Ngu vi Huong xanh")
    assert matches[0]["code"] == "BONV01"
    assert matches[0]["score"] == 999


def test_suggest_matches_ranks_by_word_overlap_without_an_alias(conn):
    _seed_product(conn, "GAO001", cost=277, name="Gạo Jasmin Aroy-D Thái Lan 4,5 Kg")
    _seed_product(conn, "GAO005", cost=110, name="Gạo Tròn Kuban Loại 1 25 Kg")

    matches = suggest_matches(conn, "Kubanskii ris DONSKOI Nishiki kuban vysshee sort GOST 20 kg")
    codes = [m["code"] for m in matches]
    assert "GAO005" in codes  # shares "Kuban"
    assert matches[0]["code"] == "GAO005"  # more overlapping words than GAO001


def test_duplicate_invoice_number_is_rejected(conn):
    # Re-importing the same delivery photo twice must not double "Bạn nợ
    # nhà cung cấp" or double-log price_history -- the partial unique
    # index exempts NULL (unnumbered drafts are still fine).
    create_invoice(conn, invoice_number="UT-3980")
    with pytest.raises(sqlite3.IntegrityError):
        create_invoice(conn, invoice_number="UT-3980")

    create_invoice(conn, invoice_number=None)
    create_invoice(conn, invoice_number=None)  # two NULLs: both allowed




def test_total_unpaid_sums_only_unpaid_invoices(conn):
    from shop.core.supplier_invoices import set_paid, set_total_amount

    paid_inv = create_invoice(conn)
    set_total_amount(conn, paid_inv, 1000)
    set_paid(conn, paid_inv, True)

    unpaid_inv = create_invoice(conn)
    set_total_amount(conn, unpaid_inv, 5591)

    assert total_unpaid(conn) == 5591


def test_total_unpaid_falls_back_to_line_sum_when_header_total_is_blank(conn):
    # The owner can enter lines one by one without ever filling in the
    # header "Tổng tiền" field -- that must not silently read as 0 owed.
    inv = create_invoice(conn)  # total_amount defaults to 0
    add_line(conn, inv, raw_name="A", raw_qty=2, raw_unit="шт", raw_unit_price=100)
    add_line(conn, inv, raw_name="B", raw_qty=1, raw_unit="шт", raw_unit_price=50)
    assert total_unpaid(conn) == 250


def test_update_line_can_clear_matched_code(conn):
    _seed_product(conn, "BOCA01", cost=40)
    inv = create_invoice(conn)
    line_id = add_line(conn, inv, raw_name="x", raw_qty=1, raw_unit="шт", raw_unit_price=42, matched_code="BOCA01")

    update_line(conn, line_id, matched_code=None)  # explicit clear, not "leave as-is"
    assert list_lines(conn, inv)[0]["matched_code"] is None

    # Omitting the argument entirely must still mean "don't touch it".
    update_line(conn, line_id, matched_code="BOCA01")
    update_line(conn, line_id, raw_qty=2)
    assert list_lines(conn, inv)[0]["matched_code"] == "BOCA01"


def test_known_lines_is_empty_with_no_matched_history(conn):
    assert known_lines(conn) == []


def test_known_lines_returns_the_most_recent_raw_text_per_matched_code(conn):
    _seed_product(conn, "BUN01", cost=150, name="Bun Tuoi")
    inv1 = create_invoice(conn)
    add_line(conn, inv1, raw_name="Bun Tuoi Ha Noi (old wording)", raw_qty=2, raw_unit="шт", raw_unit_price=150, matched_code="BUN01", unit_conversion=1.0)
    inv2 = create_invoice(conn)
    add_line(conn, inv2, raw_name="Bun Tuoi Ha Noi THANH LOC 500g", raw_qty=3, raw_unit="шт", raw_unit_price=150, matched_code="BUN01", unit_conversion=1.0)

    lines = known_lines(conn)
    assert len(lines) == 1
    assert lines[0]["matched_code"] == "BUN01"
    assert lines[0]["raw_name"] == "Bun Tuoi Ha Noi THANH LOC 500g"  # the LATER line, not the first
    assert lines[0]["raw_qty"] == 3
    assert lines[0]["order_count"] == 2  # appeared on 2 distinct invoices


def test_known_lines_ranks_the_most_recurring_product_first(conn):
    _seed_product(conn, "BUN01", cost=150, name="Bun Tuoi")
    _seed_product(conn, "MAM004", cost=350, name="Nuoc Mam Chinsu")
    # BUN01 bought on 3 separate invoices, MAM004 only once.
    for _ in range(3):
        inv = create_invoice(conn)
        add_line(conn, inv, raw_name="Bun Tuoi", raw_qty=1, raw_unit="шт", raw_unit_price=150, matched_code="BUN01")
    inv = create_invoice(conn)
    add_line(conn, inv, raw_name="Chinsu", raw_qty=1, raw_unit="шт", raw_unit_price=350, matched_code="MAM004")

    lines = known_lines(conn)
    assert [l["matched_code"] for l in lines] == ["BUN01", "MAM004"]


def test_known_lines_ignores_unmatched_lines_and_one_row_per_code(conn):
    _seed_product(conn, "BUN01", cost=150)
    _seed_product(conn, "MAM004", cost=350)
    inv = create_invoice(conn)
    add_line(conn, inv, raw_name="no match yet", raw_qty=1, raw_unit="шт", raw_unit_price=100, matched_code=None)
    add_line(conn, inv, raw_name="Bun Tuoi", raw_qty=2, raw_unit="шт", raw_unit_price=150, matched_code="BUN01")
    add_line(conn, inv, raw_name="Rybnyy sous Chinsu", raw_qty=1, raw_unit="шт", raw_unit_price=350, matched_code="MAM004")

    codes = sorted(l["matched_code"] for l in known_lines(conn))
    assert codes == ["BUN01", "MAM004"]


def test_known_lines_excludes_a_product_hidden_via_xoa_khoi_danh_muc(conn):
    """"Xóa khỏi danh mục" (request 25/10/2026) sets active=0 -- a
    seasonal item bought once and then hidden must stop being suggested
    here, otherwise it keeps coming back despite "ẩn hoàn toàn"."""
    from shop.core.products import set_active

    _seed_product(conn, "BUN01", cost=150)
    _seed_product(conn, "RUOU01", cost=500, name="Rượu Tết 2026")
    inv = create_invoice(conn)
    add_line(conn, inv, raw_name="Bun Tuoi", raw_qty=2, raw_unit="шт", raw_unit_price=150, matched_code="BUN01")
    add_line(conn, inv, raw_name="Ruou Tet", raw_qty=1, raw_unit="шт", raw_unit_price=500, matched_code="RUOU01")
    set_active(conn, "RUOU01", False)

    codes = [l["matched_code"] for l in known_lines(conn)]
    assert codes == ["BUN01"]


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


def _fake_photo(key, note="", jpeg_bytes=b"\xff\xd8\xff fake jpeg"):
    return {"key": key, "note": note, "data": base64.b64encode(jpeg_bytes).decode("ascii")}


def test_sync_photos_from_bot_requires_settings(conn, tmp_path):
    with pytest.raises(SyncError):
        sync_photos_from_bot(conn, "", "secret", tmp_path)
    with pytest.raises(SyncError):
        sync_photos_from_bot(conn, "https://example.test", "", tmp_path)


def test_sync_photos_from_bot_creates_a_draft_invoice_with_the_photo_saved(conn, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen({"photos": [_fake_photo("photo:0001-aa", note="đợt về 25/10, thiếu BUN01")]}),
    )

    inserted = sync_photos_from_bot(conn, "https://example.test", "secret", tmp_path)
    assert inserted == 1

    invoices = list_invoices(conn)
    assert len(invoices) == 1
    inv = get_invoice(conn, invoices[0]["id"])
    assert inv["note"] == "đợt về 25/10, thiếu BUN01"
    assert inv["applied_at"] is None  # never auto-applies to products
    assert inv["photo_filename"]
    saved = tmp_path / inv["photo_filename"]
    assert saved.exists()
    assert saved.read_bytes() == b"\xff\xd8\xff fake jpeg"


def test_sync_photos_from_bot_does_not_duplicate_an_already_synced_photo(conn, monkeypatch, tmp_path):
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"photos": [_fake_photo("photo:0001-aa")]}))
    assert sync_photos_from_bot(conn, "https://example.test", "secret", tmp_path) == 1
    # Same key again (e.g. `since` not honored server-side, or a stale
    # cursor after the backoff margin) -- source_key is UNIQUE, must not
    # create a second draft.
    assert sync_photos_from_bot(conn, "https://example.test", "secret", tmp_path) == 0
    assert len(list_invoices(conn)) == 1


def test_sync_photos_from_bot_wraps_a_wrong_secret_in_a_vietnamese_message(conn, monkeypatch, tmp_path):
    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    with pytest.raises(SyncError, match="Mã đồng bộ"):
        sync_photos_from_bot(conn, "https://example.test", "wrong-secret", tmp_path)


def test_sync_photos_from_bot_wraps_a_non_json_response_instead_of_crashing(conn, monkeypatch, tmp_path):
    # An older/undeployed Worker build answers unknown paths with a
    # plain 200 "OK" (see bot/src/index.js's catch-all) -- json.loads()
    # on that raises ValueError, which must become a Vietnamese SyncError,
    # not escape raw into the Qt slot that calls this.
    class _PlainTextResponse:
        def read(self):
            return b"OK"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _PlainTextResponse())
    with pytest.raises(SyncError, match="deploy lại Worker"):
        sync_photos_from_bot(conn, "https://example.test", "secret", tmp_path)


def test_sync_photos_from_bot_respects_the_reset_floor_like_online_orders_does(conn, monkeypatch, tmp_path):
    # Same bug class as online_orders' sync floor (lần 17): a factory
    # reset wipes supplier_invoices, so without a floor, the next sync
    # would immediately re-pull every pre-reset test photo still sitting
    # in the bot's KV (90-day TTL) -- a reset must actually stay reset.
    from shop.core.online_orders import set_sync_floor
    from shop.core.reset import reset_transactional_data

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"photos": [_fake_photo("photo:0000000000001-aa")]}))
    assert sync_photos_from_bot(conn, "https://example.test", "secret", tmp_path) == 1

    reset_transactional_data(conn)  # also calls set_sync_floor internally
    assert list_invoices(conn) == []

    # Same pre-reset photo comes back from the bot again (ignoring
    # `since`, worst case) -- must be skipped, not re-inserted.
    assert sync_photos_from_bot(conn, "https://example.test", "secret", tmp_path) == 0
    assert list_invoices(conn) == []

    # A genuinely new photo (after the reset) still syncs normally.
    import time

    new_key = f"photo:{int(time.time() * 1000) + 60_000:013d}-bb"
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"photos": [_fake_photo(new_key)]}))
    assert sync_photos_from_bot(conn, "https://example.test", "secret", tmp_path) == 1
