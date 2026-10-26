"""The one place price math happens. Both the public-site export and the
invoice app call these functions, so a customer's invoice total and the
public price list are always computed the same way.

Everything customer-facing is whole RUB (round-half-up), computed with
Decimal so float rounding never quietly shifts a price by 1 RUB — see
CLAUDE.md for the round-half-up requirement and worked examples.
"""
from decimal import ROUND_HALF_UP, Decimal

# Default markup for a new customer, and the markup used on the public
# price website. Kept here as the single source of truth; the customers
# table's default_markup_pct column defaults to the same value.
PUBLIC_MARKUP_PCT = Decimal("7")

# Bulk-quantity lines on the shop's own price list discount the computed
# unit price by ~2% rather than following a cost-based formula.
BULK_DISCOUNT_FACTOR = Decimal("0.98")


def _d(value) -> Decimal:
    return Decimal(str(value))


def round_rub(value) -> int:
    """Round half up to the nearest whole RUB."""
    return int(_d(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def unit_price(cost_price, markup_pct=PUBLIC_MARKUP_PCT) -> int:
    """Sale price for one unit, from cost price and a markup percent."""
    cost = _d(cost_price)
    pct = _d(markup_pct)
    return round_rub(cost * (100 + pct) / 100)


def line_total(unit_price_value, qty) -> int:
    """Total for an invoice line: unit price (already whole RUB) x qty."""
    return round_rub(_d(unit_price_value) * _d(qty))


def bulk_price(unit_price_value, bulk_qty) -> int:
    """Discounted total for a bulk-quantity tier (e.g. a whole case)."""
    return round_rub(_d(unit_price_value) * _d(bulk_qty) * BULK_DISCOUNT_FACTOR)
