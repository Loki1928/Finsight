"""Category rules CRUD."""
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import CategoryRule, CanonicalEvent, User
from app.auth.dependencies import require_user
from app.canonical.categorize import categorize_event

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

CATEGORY_SUGGESTIONS = [
    "Cash Spend", "Food", "Fuel", "Groceries", "Shopping",
    "Entertainment", "Travel", "Bill Payment", "Transfer",
    "P2P Transfer", "Income", "Investments", "Loans/EMI",
    "Bank Charges", "Utilities", "Rent", "Medical", "Education",
    "Subscriptions", "Insurance", "Government", "Owner's Drawing", "Other",
]


@router.get("/rules", response_class=HTMLResponse)
def rules_list(request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_user)):
    rules = (
        db.query(CategoryRule)
        .filter((CategoryRule.user_id == user.id) | (CategoryRule.user_id.is_(None)))
        .order_by(CategoryRule.priority.asc(), CategoryRule.id.asc())
        .all()
    )
    return templates.TemplateResponse("rules.html", {
        "request": request, "rules": rules,
        "category_suggestions": CATEGORY_SUGGESTIONS,
    })


@router.post("/rules/add")
def rules_add(
    match_pattern: str = Form(...), match_type: str = Form("contains"),
    category: str = Form(...), priority: int = Form(100),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    p = match_pattern.strip()
    c = category.strip()
    if not p or not c:
        return RedirectResponse(url="/rules", status_code=303)
    if match_type not in ("contains", "exact", "regex"):
        match_type = "contains"
    rule = CategoryRule(
        match_field="merchant_raw", match_pattern=p, match_type=match_type,
        category=c, priority=max(1, min(999, priority)),
        is_active=1, times_applied=0, user_id=user.id,
    )
    db.add(rule)
    db.commit()
    return RedirectResponse(url="/rules", status_code=303)


@router.post("/rules/{rule_id}/delete")
def rules_delete(rule_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_user)):
    rule = db.query(CategoryRule).filter(
        CategoryRule.id == rule_id, CategoryRule.user_id == user.id
    ).first()
    if not rule:
        raise HTTPException(404, "Rule not found")
    db.delete(rule)
    db.commit()
    return RedirectResponse(url="/rules", status_code=303)


@router.post("/rules/{rule_id}/toggle")
def rules_toggle(rule_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_user)):
    rule = db.query(CategoryRule).filter(
        CategoryRule.id == rule_id, CategoryRule.user_id == user.id
    ).first()
    if not rule:
        raise HTTPException(404, "Rule not found")
    rule.is_active = 0 if rule.is_active else 1
    db.commit()
    return RedirectResponse(url="/rules", status_code=303)


@router.post("/rules/apply-all")
def rules_apply_all(db: Session = Depends(get_db), user: User = Depends(require_user)):
    events = (
        db.query(CanonicalEvent)
        .filter(CanonicalEvent.user_id == user.id)
        .filter(
            (CanonicalEvent.is_user_edited == 0) | (CanonicalEvent.is_user_edited.is_(None))
        )
        .all()
    )
    for e in events:
        categorize_event(e, db)
    db.commit()
    return RedirectResponse(url="/rules", status_code=303)
