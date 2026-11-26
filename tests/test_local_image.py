"""shop.ui.local_image's gallery helpers (lần 38, "Quà tặng") -- real
QImage round-trips through tmp_path, same spirit as other *_ui.py tests
driving the actual Qt code instead of only shop.core."""
from PySide6.QtGui import QImage

from shop.core.products import gallery_list, get_product, upsert_product
from shop.ui.local_image import LocalImageError, apply_gallery_photo, remove_gallery_photo


def _make_test_image(path, size=400, color=0xFF8800):
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(color)
    assert img.save(str(path), "PNG")


def test_apply_gallery_photo_appends_and_names_files_in_order(conn, monkeypatch, tmp_path):
    monkeypatch.setattr("shop.ui.local_image.site_repo_dir", lambda: tmp_path)
    upsert_product(conn, "QT10", "Test", "chai", 1000, source="test")

    src1 = tmp_path / "a.png"
    src2 = tmp_path / "b.png"
    _make_test_image(src1)
    _make_test_image(src2)

    f1 = apply_gallery_photo(conn, "QT10", src1)
    f2 = apply_gallery_photo(conn, "QT10", src2)

    assert f1 == "QT10-g1.jpg"
    assert f2 == "QT10-g2.jpg"
    assert (tmp_path / "images" / f1).exists()
    assert (tmp_path / "images" / f2).exists()
    assert gallery_list(get_product(conn, "QT10")) == [f1, f2]


def test_apply_gallery_photo_rejects_a_too_small_image(conn, monkeypatch, tmp_path):
    monkeypatch.setattr("shop.ui.local_image.site_repo_dir", lambda: tmp_path)
    upsert_product(conn, "QT11", "Test", "chai", 1000, source="test")
    src = tmp_path / "tiny.png"
    _make_test_image(src, size=100)

    import pytest

    with pytest.raises(LocalImageError):
        apply_gallery_photo(conn, "QT11", src)
    assert gallery_list(get_product(conn, "QT11")) == []


def test_remove_gallery_photo_deletes_the_file_and_the_reference(conn, monkeypatch, tmp_path):
    monkeypatch.setattr("shop.ui.local_image.site_repo_dir", lambda: tmp_path)
    upsert_product(conn, "QT12", "Test", "chai", 1000, source="test")
    src = tmp_path / "a.png"
    _make_test_image(src)
    filename = apply_gallery_photo(conn, "QT12", src)

    remove_gallery_photo(conn, "QT12", filename)

    assert gallery_list(get_product(conn, "QT12")) == []
    assert not (tmp_path / "images" / filename).exists()


def test_remove_gallery_photo_on_an_unknown_filename_is_a_no_op(conn, monkeypatch, tmp_path):
    monkeypatch.setattr("shop.ui.local_image.site_repo_dir", lambda: tmp_path)
    upsert_product(conn, "QT13", "Test", "chai", 1000, source="test")
    remove_gallery_photo(conn, "QT13", "does-not-exist.jpg")  # must not raise
    assert gallery_list(get_product(conn, "QT13")) == []
