"""
Categorization pass for CanonicalEvent rows.

V1: pure pattern-driven via app.utils.merchant_normalizer.
V1.x: will consult CategoryRule rows first so user-defined overrides
      win over the static patterns.
"""
from app.utils.merchant_normalizer import normalize_merchant


def categorize_event(event) -> None:
    """In place: set event.merchant_normalized and event.category from event.merchant_raw."""
    source = event.merchant_raw or ""
    merchant, category = normalize_merchant(source)
    event.merchant_normalized = merchant
    event.category = category
