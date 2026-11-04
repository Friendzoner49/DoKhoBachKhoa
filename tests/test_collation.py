from shop.core.products import list_products, upsert_product


def test_vietnamese_names_sort_accent_insensitively(conn):
    # Raw codepoint order would put "Đậu" after "Xì" (Đ > X); VNAME
    # collation should sort it with the other D... names instead.
    for code, name in [("A1", "Xì Dầu"), ("A2", "Đậu Đen"), ("A3", "Dừa Khô")]:
        upsert_product(conn, code, name, "goi", 100, source="test")

    names = [p["name"] for p in list_products(conn)]
    assert names.index("Đậu Đen") < names.index("Dừa Khô") < names.index("Xì Dầu")
