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


def bulk_discount(unit_price_value, qty, bulk_qty) -> int:
    """How much to knock off a line's plain total (unit_price_value * qty)
    for every COMPLETE bulk-quantity tier ("1 thùng/bao") qty contains,
    so the invoiced total matches what the public price list advertises
    as "Giá sỉ". 0 when the product has no bulk tier or qty hasn't
    reached one full tier yet.

    27/10/2026 (lần 29): discounts only floor(qty / bulk_qty) full
    tiers, not the whole qty just because it crossed the threshold once
    -- a customer buying 1 bao (bulk_qty, e.g. GAO001's 4,5kg bag) PLUS
    a few loose kg must pay bulk_price(...) for the bao and the plain
    per-kg rate for the leftover kg, not 2% off everything. Before this,
    a mixed qty like "1 bao + 1kg" (5.5) got a blanket 2% off the full
    5.5, which doesn't match how the shop actually prices a part-bao
    order.

    Kept as a separate discount rather than a discounted unit_price so
    that qty/cost_price edits on the product line (shop.core.invoices)
    never silently swallow the discount, and so unit_price * qty =
    line_total stays true everywhere else in the app (Excel export,
    invoice_profit, the RUB-integer rule in CLAUDE.md mục 2)."""
    if not bulk_qty:
        return 0
    qty_d = _d(qty)
    bulk_qty_d = _d(bulk_qty)
    if qty_d < bulk_qty_d:
        return 0
    full_tiers = int(qty_d // bulk_qty_d)
    remainder = qty_d - (full_tiers * bulk_qty_d)
    plain_total = line_total(unit_price_value, qty)
    discounted_total = full_tiers * bulk_price(unit_price_value, bulk_qty) + line_total(unit_price_value, remainder)
    return plain_total - discounted_total
