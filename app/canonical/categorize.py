"""
Categorization pass for CanonicalEvent rows.

Resolution order (first hit wins):
  1. User-defined CategoryRule rows (by priority asc, lowest number wins).
  2. Named-merchant pattern table in merchant_normalizer.
  3. UPI/NEFT/fallback logic in merchant_normalizer.

generated_description is always set from the normalizer.
"""
import re
from app.utils.merchant_normalizer import normalize_merchant_full


def _apply_rules(raw_text: str, db) -> str | None:
    if not db or not raw_text:
        return None
    try:
        from app.models.models import CategoryRule
        rules = (
            db.query(CategoryRule)
            .filter(CategoryRule.is_active == 1)
            .order_by(CategoryRule.priority.asc())
            .all()
        )
        text_lower = raw_text.lower()
        for rule in rules:
            pattern = rule.match_pattern or ""
            if rule.match_type == "contains":
                if pattern.lower() in text_lower:
                    rule.times_applied = (rule.times_applied or 0) + 1
                    return rule.category
            elif rule.match_type == "exact":
                if pattern.lower() == text_lower:
                    rule.times_applied = (rule.times_applied or 0) + 1
                    return rule.category
            elif rule.match_type == "regex":
                try:
                    if re.search(pattern, raw_text, re.IGNORECASE):
                        rule.times_applied = (rule.times_applied or 0) + 1
                        return rule.category
                except re.error:
                    pass
    except Exception:
        pass
    return None


def categorize_event(event, db=None) -> None:
    """In-place: set merchant_normalized, category, generated_description."""
    source = event.merchant_raw or ""
    merchant, category, description = normalize_merchant_full(source)
    event.merchant_normalized = merchant
    event.generated_description = description
    rule_category = _apply_rules(source, db)
    event.category = rule_category if rule_category else category
