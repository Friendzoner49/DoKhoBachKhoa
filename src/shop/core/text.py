"""Small text-normalization helpers shared across modules that need
accent-insensitive comparison: shop.db.migrate's Vietnamese collation
and shop.core.supplier_invoices' fuzzy name matching.
"""
import unicodedata


def strip_accents(s: str) -> str:
    # Đ/đ have no canonical Unicode decomposition (they're not "D" + a
    # combining mark), so NFD alone leaves them as the highest-codepoint
    # letter in the alphabet; map them to d/D explicitly first.
    s = s.replace("Đ", "D").replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def normalize(s: str) -> str:
    """Accent-insensitive, case-insensitive, whitespace-collapsed key --
    used both as an exact-match alias key and as the basis for token
    overlap scoring."""
    return " ".join(strip_accents(s).lower().split())
