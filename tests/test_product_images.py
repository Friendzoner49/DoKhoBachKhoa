import json

from shop.core.product_images import load_manifest, record_image
from shop.core.products import get_product, upsert_product


def test_record_image_updates_manifest_and_product_image_filename(conn, tmp_path):
    upsert_product(conn, "X1", "Test", "goi", 100, source="test")
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    record_image(conn, images_dir, "X1", "X1.jpg", (800, 600), source_url="Chọn từ máy: photo.jpg")

    assert get_product(conn, "X1")["image_filename"] == "X1.jpg"
    manifest = load_manifest(images_dir)
    assert manifest["X1"]["size"] == [800, 600]
    assert manifest["X1"]["source_url"] == "Chọn từ máy: photo.jpg"
    assert manifest["X1"]["source_page"] is None


def test_record_image_preserves_other_products_entries_in_the_shared_manifest(conn, tmp_path):
    upsert_product(conn, "X1", "A", "goi", 100, source="test")
    upsert_product(conn, "X2", "B", "goi", 100, source="test")
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    record_image(conn, images_dir, "X1", "X1.jpg", (800, 600), source_url="u1")
    record_image(conn, images_dir, "X2", "X2.jpg", (900, 700), source_url="u2")

    manifest = load_manifest(images_dir)
    assert set(manifest) == {"X1", "X2"}
    assert manifest["X1"]["source_url"] == "u1"
    assert manifest["X2"]["source_url"] == "u2"


def test_load_manifest_returns_empty_dict_for_a_missing_or_corrupt_file(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    assert load_manifest(images_dir) == {}

    (images_dir / "manifest.json").write_text("{not valid json", encoding="utf-8")
    assert load_manifest(images_dir) == {}
