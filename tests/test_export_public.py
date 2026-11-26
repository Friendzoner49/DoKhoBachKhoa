"""shop.tools.export_public builds the public website's JSON -- make sure
fields that must never reach the web (cost price, Russian name used only
for cross-checking supplier invoices, lần 38 request) never leak in,
even if someone adds a careless **product-dict spread later."""
from shop.core.products import set_description, set_ingredients, set_food_tab_always, set_gallery_filenames, set_sale_until, upsert_product
from shop.core.stock import set_stock_limit
from shop.tools.export_public import build_payload


def test_show_food_tab_is_only_exported_when_the_owner_turned_it_on(conn):
    assert "show_food_tab" not in build_payload(conn)
    set_food_tab_always(conn, True)
    assert build_payload(conn)["show_food_tab"] is True
    set_food_tab_always(conn, False)
    assert "show_food_tab" not in build_payload(conn)


def test_build_payload_never_includes_name_ru_or_cost_price(conn):
    upsert_product(
        conn, "RU1", "Test product", "goi", 123.45,
        name_ru="Тестовый продукт -- секрет", source="test",
    )
    payload = build_payload(conn)
    entry = next(item for item in payload["items"] if item["code"] == "RU1")
    assert "name_ru" not in entry
    assert "cost_price" not in entry
    assert "Тестовый" not in str(entry)


def test_ordinary_product_never_gets_images_or_description_keys(conn):
    upsert_product(conn, "PLAIN1", "Mi goi thuong", "goi", 30, source="test")
    payload = build_payload(conn)
    entry = next(item for item in payload["items"] if item["code"] == "PLAIN1")
    assert "images" not in entry
    assert "description" not in entry


def test_ingredients_are_exported_only_when_filled_and_survive_a_price_edit(conn):
    upsert_product(conn, "XOI1", "Xoi", "suat", 100, source="test")
    assert "ingredients" not in build_payload(conn)["items"][0]
    set_ingredients(conn, "XOI1", "Nếp\nHành phi")
    upsert_product(conn, "XOI1", "Xoi", "suat", 120, source="test")
    assert build_payload(conn)["items"][0]["ingredients"] == "Nếp\nHành phi"


def test_special_product_with_gallery_and_description_exports_both(conn):
    upsert_product(conn, "QT1", "Beluga mau thu", "chai", 1700, category="Quà tặng", source="test")
    set_gallery_filenames(conn, "QT1", ["QT1-g1.jpg", "QT1-g2.jpg"])
    set_description(conn, "QT1", "Phien ban dac biet, chi con so luong gioi han.")
    payload = build_payload(conn)
    entry = next(item for item in payload["items"] if item["code"] == "QT1")
    assert entry["description"] == "Phien ban dac biet, chi con so luong gioi han."
    # Gallery files don't exist on disk in this test -- _image_ref()
    # drops anything missing, so "images" simply isn't added rather than
    # pointing at a broken URL. The next test covers files that do exist.
    assert "images" not in entry


def test_special_product_gallery_images_point_at_files_that_exist(conn, monkeypatch, tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "QT2.jpg").write_bytes(b"cover")
    (images_dir / "QT2-g1.jpg").write_bytes(b"angle1")
    (images_dir / "QT2-g2.jpg").write_bytes(b"angle2")
    monkeypatch.setattr("shop.tools.export_public.site_repo_dir", lambda: tmp_path)

    upsert_product(conn, "QT2", "Beluga mau vang", "chai", 1400, category="Quà tặng", source="test")
    from shop.core.products import set_image_filename

    set_image_filename(conn, "QT2", "QT2.jpg")
    set_gallery_filenames(conn, "QT2", ["QT2-g1.jpg", "QT2-g2.jpg", "missing.jpg"])

    payload = build_payload(conn)
    entry = next(item for item in payload["items"] if item["code"] == "QT2")
    assert len(entry["images"]) == 3  # cover + 2 real gallery files, "missing.jpg" dropped
    assert entry["images"][0] == entry["image"]  # cover photo shown first


def test_bulk_qty_one_exports_the_bulk_price_as_the_price(conn):
    """A product sold only as whole bags (unit "bao", bulk_qty=1): every unit
    is a bulk pack, so the site and bot just see the 2%-off price."""
    upsert_product(conn, "GAO002", "Gạo St25", "bao", 1500, bulk_qty=1, source="test")
    item = next(i for i in build_payload(conn)["items"] if i["code"] == "GAO002")
    assert item["price"] == 1573
    assert "bulk_qty" not in item and "bulk_price" not in item


def test_stock_keys_only_on_a_limited_dish_and_start_date_stays_private(conn):
    upsert_product(conn, "PLAIN2", "Hang thuong", "goi", 30, source="test")
    upsert_product(conn, "XOI", "Xoi", "suat", 0, source="test")
    set_sale_until(conn, "XOI", "2099-12-31")
    set_stock_limit(conn, "XOI", 8)
    items = {i["code"]: i for i in build_payload(conn)["items"]}
    assert {"stock_limit", "remaining", "stock_after"} <= set(items["XOI"])
    assert not {"stock_limit", "remaining", "stock_after"} & set(items["PLAIN2"])
    assert "stock_since" not in str(items)


def test_deadline_is_published_for_dishes_only_with_the_offset(conn):
    upsert_product(conn, "PLAIN3", "Hang thuong", "goi", 30, source="test")
    upsert_product(conn, "XOI2", "Xoi", "suat", 30, source="test")
    set_sale_until(conn, "XOI2", "2099-12-31", "20:00")
    items = {i["code"]: i for i in build_payload(conn)["items"]}
    assert "deadline" not in items["PLAIN3"]
    assert items["XOI2"]["deadline"].startswith("2099-12-31T20:00:00")
    assert items["XOI2"]["deadline"][19] in "+-"
