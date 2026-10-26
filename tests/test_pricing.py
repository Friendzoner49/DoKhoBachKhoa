from shop.core.pricing import bulk_price, line_total, round_rub, unit_price


def test_round_rub_half_up():
    assert round_rub(374.5) == 375
    assert round_rub(160.5) == 161
    assert round_rub(2.5) == 3


def test_unit_price_exact_half_cases():
    assert unit_price(150, 7) == 161
    assert unit_price(50, 13) == 57
    assert unit_price(10, 15) == 12


def test_unit_price_matches_shop_price_list_examples():
    # From the shop's own price list (bang gia do kho 24.11.2023.xlsx,
    # sheet BANG GIA HUP), cost x 1.07.
    assert unit_price(350, 7) == 375  # BADAM1
    assert unit_price(1300, 7) == 1391  # CAFE02
    assert unit_price(4500, 7) == 4815  # NOICOM


def test_line_total():
    assert line_total(161, 2) == 322


def test_bulk_price_matches_shop_price_list():
    # GAO005: unit price 118, bulk qty 25 -> 2891 in the shop's list.
    assert bulk_price(118, 25) == 2891
    # MT0001: unit price 59, bulk qty 30 -> 1735.
    assert bulk_price(59, 30) == 1735
