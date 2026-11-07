"""shop.tools.export_public builds the public website's JSON -- make sure
fields that must never reach the web (cost price, Russian name used only
for cross-checking supplier invoices, lần 38 request) never leak in,
even if someone adds a careless **product-dict spread later."""
from shop.core.products import set_description, set_gallery_filenames, upsert_product
from shop.tools.export_public import build_payload


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
