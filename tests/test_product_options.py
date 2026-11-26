"""Multi-size dishes (20/11/2026): every size stays its own product code;
products sharing option_group show as ONE dish on the web (size picker)
and in ONE channel post."""
import json

from shop.core import channel_announce
from shop.core.channel_announce import announce_product, build_caption
from shop.core.products import (
    get_product,
    list_option_groups,
    option_siblings,
    set_fixed_price,
    set_image_filename,
    set_option,
    set_sale_until,
    upsert_product,
)
from shop.tools.export_public import build_payload


def _seed(conn):
    for code, name, cost, price, label in [
        ("BGOI05", "Bánh gối – set 5 chiếc", 140, 550, "Set 5 chiếc"),
        ("BGOI03", "Bánh gối – set 3 chiếc", 84, 350, "Set 3 chiếc"),
    ]:
        upsert_product(conn, code, name, "set", cost, source="test")
        set_sale_until(conn, code, "2099-12-31")
        set_fixed_price(conn, code, price)
        set_option(conn, code, " Bánh gối ", label)


def test_set_option_trims_and_blank_group_clears_both(conn):
    _seed(conn)
    assert get_product(conn, "BGOI03")["option_group"] == "Bánh gối"
    assert list_option_groups(conn) == ["Bánh gối"]
    set_option(conn, "BGOI03", "  ", "Set 3 chiếc")
    p = get_product(conn, "BGOI03")
    assert (p["option_group"], p["option_label"]) == (None, None)


def test_upsert_never_wipes_the_option(conn):
    _seed(conn)
    upsert_product(conn, "BGOI03", "Bánh gối – set 3 chiếc", "set", 90, source="test")
    assert get_product(conn, "BGOI03")["option_label"] == "Set 3 chiếc"


def test_siblings_are_cheapest_first(conn):
    _seed(conn)
    codes = [s["code"] for s in option_siblings(conn, get_product(conn, "BGOI05"))]
    assert codes == ["BGOI03", "BGOI05"]


def test_export_adds_group_keys_only_to_grouped_products(conn):
    _seed(conn)
    upsert_product(conn, "PLAIN1", "Mi goi", "goi", 30, source="test")
    items = {i["code"]: i for i in build_payload(conn)["items"]}
    assert (items["BGOI03"]["group"], items["BGOI03"]["option"]) == ("Bánh gối", "Set 3 chiếc")
    assert items["BGOI03"]["price"] == 350
    assert "group" not in items["PLAIN1"] and "option" not in items["PLAIN1"]
    assert "option_group" not in items["BGOI03"] and "option_label" not in items["BGOI03"]


def test_caption_lists_every_size_once(conn):
    _seed(conn)
    p = get_product(conn, "BGOI05")
    caption = build_caption(p, option_siblings(conn, p))
    assert caption.splitlines()[:3] == ["🆕 Bánh gối", "• Set 3 chiếc: 350 RUB", "• Set 5 chiếc: 550 RUB"]
    assert "Nhận đặt đến hết" in caption


def test_edit_dialog_shows_and_returns_the_option(qapp, conn):
    from shop.ui.dialogs import ProductDialog

    _seed(conn)
    dlg = ProductDialog(product=get_product(conn, "BGOI03"), option_groups=list_option_groups(conn))
    assert dlg.option_value() == ("Bánh gối", "Set 3 chiếc")
    dlg.grocery_radio.setChecked(True)
    assert dlg.option_value() == (None, None)
    assert dlg.option_group_combo.isHidden()


def test_announce_uses_the_dish_photo_and_marks_every_size(conn, tmp_path, monkeypatch):
    _seed(conn)
    (tmp_path / "BGOI03.jpg").write_bytes(b"jpg")
    set_image_filename(conn, "BGOI03", "BGOI03.jpg")  # only the cheapest size has a photo
    sent = {}

    class _Resp:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _open(req, timeout=None):
        sent.update(json.loads(req.data))
        return _Resp()

    monkeypatch.setattr(channel_announce.urllib.request, "urlopen", _open)
    announce_product(conn, "BGOI05", "https://example.test", "secret", tmp_path)

    assert sent["filename"] == "BGOI03.jpg"
    assert "Set 5 chiếc: 550 RUB" in sent["caption"]
    assert get_product(conn, "BGOI03")["channel_announced_at"]
    assert get_product(conn, "BGOI05")["channel_announced_at"]
