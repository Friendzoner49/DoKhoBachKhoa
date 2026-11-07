from shop.core.pricing import bulk_discount, bulk_price, line_total, round_rub, unit_price


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


def test_bulk_discount_reconciles_the_plain_line_total_down_to_bulk_price():
    # The invoice keeps unit_price * qty = line_total (see
    # shop.core.invoices._resync_bulk_discount) -- bulk_discount is the
    # separate line that knocks the plain total down to what the public
    # price list already advertises as "Giá sỉ" for exactly bulk_qty.
    for price, bulk_qty in [(118, 25), (59, 30)]:
        plain_total = line_total(price, bulk_qty)
        discount = bulk_discount(price, bulk_qty, bulk_qty)
        assert plain_total - discount == bulk_price(price, bulk_qty)


def test_bulk_discount_zero_below_the_threshold():
    assert bulk_discount(59, 29, 30) == 0


def test_bulk_discount_zero_when_product_has_no_bulk_tier():
    assert bulk_discount(59, 100, 0) == 0


def test_bulk_discount_applies_per_complete_tier_not_to_the_whole_qty():
    # 27/10/2026 (lần 29): a qty past the threshold that ISN'T an exact
    # multiple of bulk_qty only gets the sỉ rate on the complete
    # tier(s); the leftover is billed at the plain rate, same as a
    # customer buying "1 thùng + vài gói lẻ" actually pays in practice.
    price, bulk_qty = 59, 30
    discount = bulk_discount(price, 35, bulk_qty)
    expected_total = bulk_price(price, bulk_qty) + line_total(price, 5)  # 1 full thùng + 5 loose
    assert line_total(price, 35) - discount == expected_total


def test_bulk_discount_applies_to_every_complete_tier_in_an_exact_multiple():
    price, bulk_qty = 59, 30
    discount = bulk_discount(price, 60, bulk_qty)  # exactly 2 thùng, no leftover
    assert line_total(price, 60) - discount == 2 * bulk_price(price, bulk_qty)


def test_bulk_discount_matches_the_gao001_whole_bag_plus_loose_kg_example():
    # GAO001: 297 ₽/kg, bulk_qty 4.5 (one 4,5kg bao) -> bulk_price 1310.
    # Buying 1 bao + 1kg loose must charge 1310 + 297 = 1607, not a
    # blanket 2% off the full 5.5kg.
    price, bulk_qty = 297, 4.5
    assert bulk_price(price, bulk_qty) == 1310
    discount = bulk_discount(price, 5.5, bulk_qty)
    assert line_total(price, 5.5) - discount == 1607
    # 2 full bao (9kg), no leftover -> exactly 2 x 1310.
    discount_2_bao = bulk_discount(price, 9, bulk_qty)
    assert line_total(price, 9) - discount_2_bao == 2620


def test_bulk_price_override_is_used_clamped_and_optional():
    from shop.core.pricing import bulk_discount, effective_bulk_price

    # 5kg bag, retail 300/kg: formula 0.98 x 1500 = 1470; the owner's exception wins
    assert effective_bulk_price(300, 5) == 1470
    assert effective_bulk_price(300, 5, 1300) == 1300
    assert effective_bulk_price(300, 5, None) == 1470
    # never above the plain price of the same quantity (low-markup customer: 250/kg -> 1250)
    assert effective_bulk_price(250, 5, 1300) == 1250
    # discount line = plain total - bag price
    assert bulk_discount(300, 5, 5, 1300) == 1500 - 1300
    assert bulk_discount(300, 6, 5, 1300) == 1800 - (1300 + 300)
