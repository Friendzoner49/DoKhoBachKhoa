from shop.core.products import get_product, set_active, set_bulk_unit, set_in_stock, upsert_product


def test_editing_a_product_preserves_its_inactive_state(conn):
    """Regression test: the product-edit dialog doesn't expose active/
    category, so the UI must pass the existing values through to
    upsert_product rather than letting it default back to active=True.
    This exercises the same call shop.ui.products_page.edit_product
    makes."""
    upsert_product(conn, "X1", "Test", "goi", 100, source="test")
    set_active(conn, "X1", False)
    product = get_product(conn, "X1")
    assert product["active"] == 0

    upsert_product(
        conn,
        code="X1",
        name="Test edited",
        unit="goi",
        cost_price=120,
        bulk_qty=0,
        active=product["active"],
        category=product["category"],
        source="test",
    )
    assert get_product(conn, "X1")["active"] == 0


def test_new_product_defaults_to_in_stock(conn):
    upsert_product(conn, "X2", "Test", "goi", 100, source="test")
    assert get_product(conn, "X2")["in_stock"] == 1


def test_editing_a_product_preserves_its_out_of_stock_flag(conn):
    """Regression test for the same class of bug as the "active" one
    above: a seasonal item (e.g. Ca Basa, Ke Ga) gets flagged "tam het
    hang" via set_in_stock, independently of being discontinued -- an
    unrelated price edit through the app must not silently clear it."""
    upsert_product(conn, "X3", "Test", "goi", 100, source="test")
    set_in_stock(conn, "X3", False)
    product = get_product(conn, "X3")
    assert product["in_stock"] == 0

    upsert_product(
        conn,
        code="X3",
        name="Test edited",
        unit="goi",
        cost_price=120,
        bulk_qty=0,
        active=product["active"],
        category=product["category"],
        source="test",
    )
    assert get_product(conn, "X3")["in_stock"] == 0


def test_new_product_defaults_to_blank_bulk_unit(conn):
    upsert_product(conn, "X4", "Test", "goi", 100, source="test")
    assert get_product(conn, "X4")["bulk_unit"] == ""


def test_set_bulk_unit_then_upsert_without_it_preserves_it(conn):
    """Regression for the lần 36 case: "Áp dụng giá mới" from a supplier
    invoice (shop.core.supplier_invoices.apply_invoice) only carries
    code/name/unit/cost_price/bulk_qty -- it has never heard of
    bulk_unit, so it must not silently blank out a pack label typed in
    once through ProductDialog."""
    upsert_product(conn, "X5", "Test", "goi", 100, bulk_qty=30, source="test")
    set_bulk_unit(conn, "X5", "thùng")
    assert get_product(conn, "X5")["bulk_unit"] == "thùng"

    upsert_product(
        conn,
        code="X5",
        name="Test edited",
        unit="goi",
        cost_price=120,
        bulk_qty=30,
        source="supplier-invoice-test",  # no bulk_unit kwarg, like apply_invoice()
    )
    assert get_product(conn, "X5")["bulk_unit"] == "thùng"


def test_product_dialog_can_explicitly_clear_bulk_unit(conn):
    """ProductDialog always passes bulk_unit="" explicitly when the field
    is left blank (see shop.ui.dialogs.ProductDialog.values) -- that must
    actually clear a previously-set label, unlike the implicit None-means-
    keep default."""
    upsert_product(conn, "X6", "Test", "goi", 100, bulk_qty=30, bulk_unit="thùng", source="test")
    upsert_product(conn, "X6", "Test", "goi", 100, bulk_qty=30, bulk_unit="", source="test")
    assert get_product(conn, "X6")["bulk_unit"] == ""


def test_new_product_defaults_to_blank_name_ru(conn):
    upsert_product(conn, "X7", "Test", "goi", 100, source="test")
    assert get_product(conn, "X7")["name_ru"] == ""


def test_upsert_without_name_ru_kwarg_preserves_it(conn):
    """Same guarantee as bulk_unit (lần 36): "Áp dụng giá mới" from a
    supplier invoice never carries name_ru, so re-applying a price must
    not silently blank out a Russian name typed in once through
    ProductDialog."""
    upsert_product(conn, "X8", "Test", "goi", 100, name_ru="Тест", source="test")
    upsert_product(
        conn,
        code="X8",
        name="Test edited",
        unit="goi",
        cost_price=120,
        source="supplier-invoice-test",  # no name_ru kwarg, like apply_invoice()
    )
    assert get_product(conn, "X8")["name_ru"] == "Тест"


def test_product_dialog_can_explicitly_clear_name_ru(conn):
    upsert_product(conn, "X9", "Test", "goi", 100, name_ru="Тест", source="test")
    upsert_product(conn, "X9", "Test", "goi", 100, name_ru="", source="test")
    assert get_product(conn, "X9")["name_ru"] == ""


def test_new_product_defaults_to_empty_gallery_and_description(conn):
    from shop.core.products import gallery_list

    upsert_product(conn, "QT01", "Test", "chai", 1000, source="test")
    product = get_product(conn, "QT01")
    assert gallery_list(product) == []
    assert product["description"] == ""


def test_set_gallery_filenames_round_trips_order(conn):
    from shop.core.products import gallery_list, set_gallery_filenames

    upsert_product(conn, "QT02", "Test", "chai", 1000, source="test")
    set_gallery_filenames(conn, "QT02", ["QT02-g1.jpg", "QT02-g2.jpg", "QT02-g3.jpg"])
    assert gallery_list(get_product(conn, "QT02")) == ["QT02-g1.jpg", "QT02-g2.jpg", "QT02-g3.jpg"]


def test_set_description_then_upsert_without_it_is_unaffected(conn):
    """description is managed outside upsert_product (like sale_until) --
    re-applying a price from a supplier invoice must never touch it."""
    from shop.core.products import set_description

    upsert_product(conn, "QT03", "Test", "chai", 1000, source="test")
    set_description(conn, "QT03", "Phiên bản đặc biệt.")
    upsert_product(conn, "QT03", "Test edited", "chai", 1100, source="supplier-invoice-test")
    assert get_product(conn, "QT03")["description"] == "Phiên bản đặc biệt."
