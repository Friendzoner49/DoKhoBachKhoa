from shop.core.products import get_product, set_active, set_in_stock, upsert_product


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
