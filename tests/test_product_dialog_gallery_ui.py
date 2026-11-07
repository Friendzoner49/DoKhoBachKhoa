"""ProductDialog's gallery/description UI (lần 38, "Quà tặng") and the
deferred-apply wiring in ProductsPage (same pattern as the single cover
photo, see test_products_page_ui.py)."""
from PySide6.QtGui import QImage

from shop.core.products import gallery_list, get_product, upsert_product
from shop.ui.dialogs import ProductDialog
from shop.ui.products_page import ProductsPage


def _make_test_image(path, size=400):
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(0xFF8800)
    assert img.save(str(path), "PNG")


def test_dialog_tracks_pending_gallery_additions_without_touching_disk_yet(qapp, tmp_path):
    dialog = ProductDialog(None)
    src = tmp_path / "a.png"
    _make_test_image(src)
    dialog._gallery_pending_add.append(src)
    dialog._refresh_gallery_widget()

    assert dialog.gallery_additions() == [src]
    assert dialog.gallery_list_widget.count() == 1


def test_dialog_tracks_pending_removal_of_an_existing_filename(qapp, conn):
    from shop.core.products import set_gallery_filenames

    upsert_product(conn, "QTREM", "Test", "chai", 1000, source="test")
    set_gallery_filenames(conn, "QTREM", ["QT-g1.jpg", "QT-g2.jpg"])
    product = get_product(conn, "QTREM")
    dialog = ProductDialog(None, product=product)
    dialog.gallery_list_widget.setCurrentRow(0)
    dialog._remove_selected_gallery_image()

    assert dialog.gallery_removals() == ["QT-g1.jpg"]
    assert dialog.gallery_list_widget.count() == 1  # removed one shown, no longer listed


def test_products_page_edit_applies_gallery_additions_and_description(qapp, conn, monkeypatch, tmp_path):
    monkeypatch.setattr("shop.ui.local_image.site_repo_dir", lambda: tmp_path)
    monkeypatch.setattr("shop.ui.dialogs.site_repo_dir", lambda: tmp_path)
    upsert_product(conn, "QT20", "Beluga test", "chai", 1700, category="Quà tặng", source="test")

    src = tmp_path / "a.png"
    _make_test_image(src)

    def _accept_and_add_photo(self):
        self.description_edit.setPlainText("Phiên bản giới hạn.")
        self._gallery_pending_add.append(src)
        return True

    monkeypatch.setattr(ProductDialog, "exec", _accept_and_add_photo)

    page = ProductsPage(conn)
    page.table.selectRow(0)
    page.edit_product()

    product = get_product(conn, "QT20")
    assert product["description"] == "Phiên bản giới hạn."
    gallery = gallery_list(product)
    assert gallery == ["QT20-g1.jpg"]
    assert (tmp_path / "images" / "QT20-g1.jpg").exists()
