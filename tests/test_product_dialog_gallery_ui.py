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
        self.ingredients_edit.setPlainText("Tiêu, hành")
        self._gallery_pending_add.append(src)
        return True

    monkeypatch.setattr(ProductDialog, "exec", _accept_and_add_photo)

    page = ProductsPage(conn)
    page.table.selectRow(0)
    page.edit_product()

    product = get_product(conn, "QT20")
    assert product["description"] == "Phiên bản giới hạn."
    assert product["ingredients"] == ""  # a grocery item never gets ingredients
    gallery = gallery_list(product)
    assert gallery == ["QT20-g1.jpg"]
    assert (tmp_path / "images" / "QT20-g1.jpg").exists()


def test_each_item_type_shows_only_its_own_rows(qapp):
    dialog = ProductDialog(None)  # "Thêm mặt hàng" starts as a pre-order dish
    dish_only = [dialog.fixed_price_spin, dialog.stock_limit_spin, dialog.option_group_combo, dialog.option_label_edit]
    grocery_only = [dialog.category_combo, dialog.bulk_qty_spin, dialog.bulk_override_check,
                    dialog.bulk_override_spin, dialog.bulk_unit_edit, dialog.name_ru_edit]
    assert dialog.is_dish() and dialog.sale_until_value()
    assert not any(w.isHidden() for w in dish_only) and all(w.isHidden() for w in grocery_only)
    assert dialog._text_tabs.isTabVisible(1)

    dialog.ingredients_edit.setPlainText("Tiêu")
    dialog.grocery_radio.setChecked(True)
    assert all(w.isHidden() for w in dish_only) and not any(w.isHidden() for w in grocery_only)
    assert not dialog._text_tabs.isTabVisible(1)
    assert dialog.sale_until_value() is None and dialog.ingredients_value() == ""


def test_dish_keeps_hidden_grocery_fields_and_its_ingredients(qapp, conn):
    from shop.core.products import set_ingredients, set_sale_until

    upsert_product(conn, "M1", "Mon", "suat", 100, category="Bánh kẹo", bulk_qty=5, bulk_unit="thùng",
                   name_ru="Блюдо", source="test")
    set_sale_until(conn, "M1", "2030-01-01")
    set_ingredients(conn, "M1", "Tiêu")
    dialog = ProductDialog(None, product=get_product(conn, "M1"))

    assert dialog.is_dish() and dialog.ingredients_value() == "Tiêu"
    values = dialog.values()
    assert (values["category"], values["bulk_qty"], values["bulk_unit"], values["name_ru"]) == (
        "Bánh kẹo", 5, "thùng", "Блюдо")
