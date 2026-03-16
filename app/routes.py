import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.database import get_db
from app.models import (
    MonthlyPeriod,
    Transaction,
    CardPurchase,
    CustomSubcategory,
    CustomCategory,
    CreditCard,
    CATEGORY_LABELS,
    CARD_SUBCATEGORY_LABELS,
)
from app.schemas import (
    MonthlyPeriodCreate,
    MonthlyPeriodUpdate,
    MonthlyPeriodResponse,
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    MonthlySummary,
    CardPurchaseCreate,
    CardPurchaseResponse,
    CreditCardCreate,
    CreditCardResponse,
    InsightItem,
    PeriodInsightsResponse,
    StatementParseRequest,
    StatementParseResponse,
    StatementLinePreview,
    StatementImportRequest,
    NLParseRequest,
    NLParseResponse,
    NLParseItem,
)

router = APIRouter(prefix="/api")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _next_month(year: int, month: int) -> tuple[int, int]:
    """Return (year, month) for the next month."""
    if month == 12:
        return year + 1, 1
    return year, month + 1


def _prev_month(year: int, month: int) -> tuple[int, int]:
    """Return (year, month) for the previous month."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


def get_or_create_period(db: Session, year: int, month: int, reference_period: MonthlyPeriod) -> MonthlyPeriod:
    """Get or create a period, copying the blue rate from the reference."""
    period = db.query(MonthlyPeriod).filter(
        MonthlyPeriod.year == year, MonthlyPeriod.month == month
    ).first()
    if not period:
        period = MonthlyPeriod(
            year=year, month=month,
            blue_dollar_rate=reference_period.blue_dollar_rate,
            notes=""
        )
        db.add(period)
        db.flush()
    return period


def _pct_change(old: float, new: float) -> tuple[float | None, str]:
    """Compute % change and direction."""
    if old == 0 and new == 0:
        return None, "stable"
    if old == 0:
        return None, "new"
    pct = ((new - old) / old) * 100
    if abs(pct) < 3:
        return round(pct, 1), "stable"
    return round(pct, 1), "up" if pct > 0 else "down"


def _category_totals(transactions: list, rate: float) -> dict[str, float]:
    """Sum expenses by category in ARS."""
    totals: dict[str, float] = {}
    for t in transactions:
        if t.transaction_type != "expense":
            continue
        amount_ars = t.amount * rate if t.currency == "USD" else t.amount
        totals[t.category] = totals.get(t.category, 0) + amount_ars
    return totals


def _subcategory_totals(transactions: list, rate: float) -> dict[str, float]:
    """Sum tarjeta expenses by subcategory in ARS."""
    totals: dict[str, float] = {}
    for t in transactions:
        if t.transaction_type != "expense" or t.category != "tarjeta":
            continue
        sub = t.subcategory or "otros"
        amount_ars = t.amount * rate if t.currency == "USD" else t.amount
        totals[sub] = totals.get(sub, 0) + amount_ars
    return totals


# ── Monthly Periods ──────────────────────────────────────────────────────────


@router.get("/periods", response_model=list[MonthlyPeriodResponse])
def list_periods(db: Session = Depends(get_db)):
    return db.query(MonthlyPeriod).order_by(MonthlyPeriod.year.desc(), MonthlyPeriod.month.desc()).all()


@router.post("/periods", response_model=MonthlyPeriodResponse, status_code=201)
def create_period(data: MonthlyPeriodCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(MonthlyPeriod)
        .filter(MonthlyPeriod.year == data.year, MonthlyPeriod.month == data.month)
        .first()
    )
    if existing:
        raise HTTPException(400, "Period already exists")
    period = MonthlyPeriod(**data.model_dump())
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


@router.get("/periods/{period_id}", response_model=MonthlyPeriodResponse)
def get_period(period_id: int, db: Session = Depends(get_db)):
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")
    return period


@router.patch("/periods/{period_id}", response_model=MonthlyPeriodResponse)
def update_period(period_id: int, data: MonthlyPeriodUpdate, db: Session = Depends(get_db)):
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(period, key, value)
    db.commit()
    db.refresh(period)
    return period


@router.delete("/periods/{period_id}", status_code=204)
def delete_period(period_id: int, db: Session = Depends(get_db)):
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")
    db.query(Transaction).filter(Transaction.period_id == period_id).delete()
    db.delete(period)
    db.commit()


# ── Transactions ─────────────────────────────────────────────────────────────


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions(period_id: int = None, db: Session = Depends(get_db)):
    q = db.query(Transaction)
    if period_id:
        q = q.filter(Transaction.period_id == period_id)
    return q.order_by(Transaction.date.desc()).all()


@router.post("/transactions", response_model=TransactionResponse, status_code=201)
def create_transaction(data: TransactionCreate, db: Session = Depends(get_db)):
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == data.period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")
    dump = data.model_dump()
    if not dump["date"]:
        dump["date"] = date.today()
    elif isinstance(dump["date"], str):
        dump["date"] = date.fromisoformat(dump["date"])
    txn = Transaction(**dump)
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.get("/transactions/{txn_id}", response_model=TransactionResponse)
def get_transaction(txn_id: int, db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    return txn


@router.patch("/transactions/{txn_id}", response_model=TransactionResponse)
def update_transaction(txn_id: int, data: TransactionUpdate, db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    updates = data.model_dump(exclude_unset=True)
    if "date" in updates and updates["date"] is not None:
        updates["date"] = date.fromisoformat(updates["date"])
    for key, value in updates.items():
        setattr(txn, key, value)
    db.commit()
    db.refresh(txn)
    return txn


@router.delete("/transactions/card-bulk/{period_id}", status_code=200)
def delete_all_card_transactions(period_id: int, db: Session = Depends(get_db)):
    """Delete all tarjeta transactions for a given period."""
    count = db.query(Transaction).filter(
        Transaction.period_id == period_id,
        Transaction.category == "tarjeta",
    ).delete()
    db.commit()
    return {"message": f"Se eliminaron {count} consumos de tarjeta", "count": count}


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    db.delete(txn)
    db.commit()


# ── Summary ──────────────────────────────────────────────────────────────────


@router.get("/summary/{period_id}", response_model=MonthlySummary)
def get_monthly_summary(period_id: int, db: Session = Depends(get_db)):
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")

    transactions = db.query(Transaction).filter(Transaction.period_id == period_id).all()
    rate = period.blue_dollar_rate

    income_ars = sum(t.amount for t in transactions if t.transaction_type == "income" and t.currency == "ARS")
    income_usd = sum(t.amount for t in transactions if t.transaction_type == "income" and t.currency == "USD")
    expense_ars = sum(t.amount for t in transactions if t.transaction_type == "expense" and t.currency == "ARS")
    expense_usd = sum(t.amount for t in transactions if t.transaction_type == "expense" and t.currency == "USD")

    total_income_converted = income_ars + (income_usd * rate)
    total_expense_converted = expense_ars + (expense_usd * rate)

    return MonthlySummary(
        period=period,
        total_income_ars=income_ars,
        total_income_usd=income_usd,
        total_income_ars_converted=total_income_converted,
        total_expenses_ars=expense_ars,
        total_expenses_usd=expense_usd,
        total_expenses_ars_converted=total_expense_converted,
        balance_ars=total_income_converted - total_expense_converted,
        transactions=transactions,
    )


# ── Seed defaults ────────────────────────────────────────────────────────────


@router.post("/periods/{period_id}/seed-defaults", status_code=201)
def seed_default_transactions(period_id: int, db: Session = Depends(get_db)):
    """Pre-populate a period with the user's recurring income & fixed expenses."""
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")

    today = date(period.year, period.month, 1)

    defaults = [
        {"description": "Salario USD", "amount": 1750, "currency": "USD", "transaction_type": "income", "category": "salary_usd", "is_fixed": True},
        {"description": "Salario ARS", "amount": 400000, "currency": "ARS", "transaction_type": "income", "category": "salary_ars", "is_fixed": True},
        {"description": "Alquiler", "amount": 915000, "currency": "ARS", "transaction_type": "expense", "category": "rent", "is_fixed": True},
        {"description": "Expensas", "amount": 170000, "currency": "ARS", "transaction_type": "expense", "category": "expensas", "is_fixed": True},
        {"description": "Expensas cochera", "amount": 60000, "currency": "ARS", "transaction_type": "expense", "category": "expensas_cochera", "is_fixed": True},
        {"description": "Maestría", "amount": 250000, "currency": "ARS", "transaction_type": "expense", "category": "maestria", "is_fixed": True},
        {"description": "EPEC", "amount": 55000, "currency": "ARS", "transaction_type": "expense", "category": "epec", "is_fixed": True},
        {"description": "Fondo común pareja", "amount": 100000, "currency": "ARS", "transaction_type": "expense", "category": "fondo_pareja", "is_fixed": True},
        {"description": "Fondo jubilación", "amount": 100, "currency": "USD", "transaction_type": "expense", "category": "fondo_jubilacion", "is_fixed": True},
    ]

    created = []
    for d in defaults:
        txn = Transaction(period_id=period_id, date=today, notes="", **d)
        db.add(txn)
        created.append(d["description"])

    db.commit()
    return {"message": f"Created {len(created)} default transactions", "items": created}


# ── Categories ───────────────────────────────────────────────────────────────


def _get_all_categories(db: Session) -> dict[str, str]:
    """Merge default categories with custom ones from DB."""
    merged = dict(CATEGORY_LABELS)
    customs = db.query(CustomCategory).all()
    for c in customs:
        merged[c.key] = c.label
    return merged


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    return _get_all_categories(db)


@router.post("/categories", status_code=201)
def create_category(data: dict, db: Session = Depends(get_db)):
    """Create a custom category. Body: {"key": "gym", "label": "Gimnasio", "type": "expense"}"""
    key = data.get("key", "").strip().lower()
    label = data.get("label", "").strip()
    cat_type = data.get("type", "expense")
    if not key or not label:
        raise HTTPException(400, "key y label son requeridos")
    key = re.sub(r'[^a-z0-9_]', '_', key)
    all_cats = _get_all_categories(db)
    if key in all_cats:
        raise HTTPException(400, f"La categoria '{key}' ya existe")
    custom = CustomCategory(key=key, label=label, category_type=cat_type)
    db.add(custom)
    db.commit()
    return _get_all_categories(db)


@router.delete("/categories/{key}", status_code=200)
def delete_category(key: str, db: Session = Depends(get_db)):
    """Delete a custom category (can't delete built-in ones)."""
    if key in CATEGORY_LABELS:
        raise HTTPException(400, "No se puede eliminar una categoria predeterminada")
    custom = db.query(CustomCategory).filter(CustomCategory.key == key).first()
    if not custom:
        raise HTTPException(404, "Categoria no encontrada")
    db.delete(custom)
    db.commit()
    return _get_all_categories(db)


def _get_all_subcategories(db: Session) -> dict[str, str]:
    """Merge default subcategories with custom ones from DB."""
    merged = dict(CARD_SUBCATEGORY_LABELS)
    customs = db.query(CustomSubcategory).all()
    for c in customs:
        merged[c.key] = c.label
    return merged


@router.get("/card-subcategories")
def list_card_subcategories(db: Session = Depends(get_db)):
    return _get_all_subcategories(db)


@router.post("/card-subcategories", status_code=201)
def create_card_subcategory(data: dict, db: Session = Depends(get_db)):
    """Create a custom card subcategory. Body: {"key": "mascotas", "label": "Mascotas"}"""
    key = data.get("key", "").strip().lower()
    label = data.get("label", "").strip()
    if not key or not label:
        raise HTTPException(400, "key y label son requeridos")
    # Remove spaces/special chars from key
    key = re.sub(r'[^a-z0-9_]', '_', key)
    # Check if already exists
    all_subs = _get_all_subcategories(db)
    if key in all_subs:
        raise HTTPException(400, f"La subcategoria '{key}' ya existe")
    custom = CustomSubcategory(key=key, label=label)
    db.add(custom)
    db.commit()
    return _get_all_subcategories(db)


@router.delete("/card-subcategories/{key}", status_code=200)
def delete_card_subcategory(key: str, db: Session = Depends(get_db)):
    """Delete a custom subcategory (can't delete built-in ones)."""
    if key in CARD_SUBCATEGORY_LABELS:
        raise HTTPException(400, "No se puede eliminar una subcategoria predeterminada")
    custom = db.query(CustomSubcategory).filter(CustomSubcategory.key == key).first()
    if not custom:
        raise HTTPException(404, "Subcategoria no encontrada")
    db.delete(custom)
    db.commit()
    return _get_all_subcategories(db)


# ── Card Purchases (Cuotas) ─────────────────────────────────────────────────


@router.get("/card-purchases", response_model=list[CardPurchaseResponse])
def list_card_purchases(period_id: int = None, db: Session = Depends(get_db)):
    q = db.query(CardPurchase)
    if period_id:
        q = q.filter(CardPurchase.source_period_id == period_id)
    return q.order_by(CardPurchase.date.desc()).all()


@router.post("/card-purchases", response_model=CardPurchaseResponse, status_code=201)
def create_card_purchase(data: CardPurchaseCreate, db: Session = Depends(get_db)):
    """Create a card purchase and auto-generate installment transactions."""
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == data.period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")

    if data.installment_current < 1 or data.installment_current > data.installments_total:
        raise HTTPException(400, "Cuota actual debe estar entre 1 y el total de cuotas")

    installment_amount = round(data.total_amount / data.installments_total, 2)
    purchase_date = date.fromisoformat(data.date) if data.date else date(period.year, period.month, 1)

    purchase = CardPurchase(
        description=data.description,
        total_amount=data.total_amount,
        installments_total=data.installments_total,
        installment_amount=installment_amount,
        subcategory=data.subcategory,
        date=purchase_date,
        source_period_id=period.id,
    )
    db.add(purchase)
    db.flush()

    # Create transactions from current installment to the last one
    y, m = period.year, period.month
    for i in range(data.installment_current, data.installments_total + 1):
        target_period = get_or_create_period(db, y, m, period)
        txn = Transaction(
            period_id=target_period.id,
            description=f"{data.description} (cuota {i}/{data.installments_total})",
            amount=installment_amount,
            currency="ARS",
            transaction_type="expense",
            category="tarjeta",
            subcategory=data.subcategory,
            date=date(y, m, 1),
            is_fixed=False,
            notes=f"Compra en cuotas - {data.description}",
            card_purchase_id=purchase.id,
            installment_number=i,
            credit_card_id=data.credit_card_id,
        )
        db.add(txn)
        y, m = _next_month(y, m)

    db.commit()
    db.refresh(purchase)
    return purchase


@router.delete("/card-purchases/{purchase_id}", status_code=204)
def delete_card_purchase(purchase_id: int, db: Session = Depends(get_db)):
    purchase = db.query(CardPurchase).filter(CardPurchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(404, "Card purchase not found")
    db.query(Transaction).filter(Transaction.card_purchase_id == purchase_id).delete()
    db.delete(purchase)
    db.commit()


# ── Insights ─────────────────────────────────────────────────────────────────


@router.get("/insights/{period_id}", response_model=PeriodInsightsResponse)
def get_insights(period_id: int, db: Session = Depends(get_db)):
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")

    # Find previous period
    py, pm = _prev_month(period.year, period.month)
    prev_period = db.query(MonthlyPeriod).filter(
        MonthlyPeriod.year == py, MonthlyPeriod.month == pm
    ).first()

    curr_txns = db.query(Transaction).filter(Transaction.period_id == period_id).all()

    if not prev_period:
        total_exp = sum(
            (t.amount * period.blue_dollar_rate if t.currency == "USD" else t.amount)
            for t in curr_txns if t.transaction_type == "expense"
        )
        total_inc = sum(
            (t.amount * period.blue_dollar_rate if t.currency == "USD" else t.amount)
            for t in curr_txns if t.transaction_type == "income"
        )
        insights = []
        if total_inc > 0:
            savings = round(((total_inc - total_exp) / total_inc) * 100, 1)
            insights.append(InsightItem(
                category="general",
                message=f"Tu tasa de ahorro este mes es del {savings}%",
                direction="stable"
            ))
        return PeriodInsightsResponse(
            period_id=period_id,
            previous_period_id=None,
            insights=insights,
            summary="Es tu primer mes registrado. ¡A partir del próximo podrás ver comparaciones!"
        )

    prev_txns = db.query(Transaction).filter(Transaction.period_id == prev_period.id).all()
    rate_curr = period.blue_dollar_rate
    rate_prev = prev_period.blue_dollar_rate

    # Total expenses comparison
    curr_exp_total = sum(
        (t.amount * rate_curr if t.currency == "USD" else t.amount)
        for t in curr_txns if t.transaction_type == "expense"
    )
    prev_exp_total = sum(
        (t.amount * rate_prev if t.currency == "USD" else t.amount)
        for t in prev_txns if t.transaction_type == "expense"
    )
    curr_inc_total = sum(
        (t.amount * rate_curr if t.currency == "USD" else t.amount)
        for t in curr_txns if t.transaction_type == "income"
    )
    prev_inc_total = sum(
        (t.amount * rate_prev if t.currency == "USD" else t.amount)
        for t in prev_txns if t.transaction_type == "income"
    )

    insights = []

    # Overall expenses
    pct, direction = _pct_change(prev_exp_total, curr_exp_total)
    if pct is not None:
        if direction == "up":
            msg = f"Tus gastos totales subieron {pct}% respecto al mes anterior"
        elif direction == "down":
            msg = f"Tus gastos totales bajaron {abs(pct)}% respecto al mes anterior"
        else:
            msg = "Tus gastos totales se mantuvieron estables"
        insights.append(InsightItem(category="general", message=msg, change_percent=pct, direction=direction))

    # Overall income
    pct, direction = _pct_change(prev_inc_total, curr_inc_total)
    if pct is not None and direction != "stable":
        if direction == "up":
            msg = f"Tus ingresos subieron {pct}%"
        else:
            msg = f"Tus ingresos bajaron {abs(pct)}%"
        insights.append(InsightItem(category="general", message=msg, change_percent=pct, direction=direction))

    # Category-level comparison
    curr_cats = _category_totals(curr_txns, rate_curr)
    prev_cats = _category_totals(prev_txns, rate_prev)
    all_cats = set(list(curr_cats.keys()) + list(prev_cats.keys()))

    for cat in all_cats:
        curr_val = curr_cats.get(cat, 0)
        prev_val = prev_cats.get(cat, 0)
        pct, direction = _pct_change(prev_val, curr_val)
        label = CATEGORY_LABELS.get(cat, cat)

        if direction == "new":
            insights.append(InsightItem(
                category=cat,
                message=f"Nuevo gasto en {label} este mes: {_fmt_ars(curr_val)}",
                direction="new"
            ))
        elif direction == "up" and pct and pct > 5:
            insights.append(InsightItem(
                category=cat,
                message=f"Tus gastos en {label} subieron {pct}%",
                change_percent=pct, direction="up"
            ))
        elif direction == "down" and pct and pct < -5:
            insights.append(InsightItem(
                category=cat,
                message=f"Tus gastos en {label} bajaron {abs(pct)}% 🎉",
                change_percent=pct, direction="down"
            ))

    # Card subcategory breakdown
    curr_subs = _subcategory_totals(curr_txns, rate_curr)
    prev_subs = _subcategory_totals(prev_txns, rate_prev)
    all_subs = set(list(curr_subs.keys()) + list(prev_subs.keys()))

    for sub in all_subs:
        curr_val = curr_subs.get(sub, 0)
        prev_val = prev_subs.get(sub, 0)
        pct, direction = _pct_change(prev_val, curr_val)
        label = CARD_SUBCATEGORY_LABELS.get(sub, sub)

        if direction == "new":
            insights.append(InsightItem(
                category=f"tarjeta:{sub}",
                message=f"Nuevo gasto con tarjeta en {label}: {_fmt_ars(curr_val)}",
                direction="new"
            ))
        elif direction == "up" and pct and pct > 5:
            insights.append(InsightItem(
                category=f"tarjeta:{sub}",
                message=f"Tus consumos con tarjeta en {label} crecieron {pct}%",
                change_percent=pct, direction="up"
            ))
        elif direction == "down" and pct and pct < -5:
            insights.append(InsightItem(
                category=f"tarjeta:{sub}",
                message=f"Tus consumos con tarjeta en {label} bajaron {abs(pct)}%",
                change_percent=pct, direction="down"
            ))

    # Savings rate
    if curr_inc_total > 0:
        curr_savings = round(((curr_inc_total - curr_exp_total) / curr_inc_total) * 100, 1)
        if prev_inc_total > 0:
            prev_savings = round(((prev_inc_total - prev_exp_total) / prev_inc_total) * 100, 1)
            diff = round(curr_savings - prev_savings, 1)
            if abs(diff) > 1:
                direction = "up" if diff > 0 else "down"
                if diff > 0:
                    msg = f"Tu tasa de ahorro mejoró: {curr_savings}% (era {prev_savings}%)"
                else:
                    msg = f"Tu tasa de ahorro bajó: {curr_savings}% (era {prev_savings}%)"
                insights.append(InsightItem(category="ahorro", message=msg, change_percent=diff, direction=direction))
        else:
            insights.append(InsightItem(
                category="ahorro",
                message=f"Tu tasa de ahorro este mes es del {curr_savings}%",
                direction="stable"
            ))

    # Summary
    if curr_exp_total > prev_exp_total:
        summary = f"Este mes gastaste más que el anterior. Revisá las categorías que más crecieron."
    elif curr_exp_total < prev_exp_total:
        summary = f"¡Buen mes! Gastaste menos que el mes anterior."
    else:
        summary = "Tus gastos se mantuvieron similares al mes anterior."

    return PeriodInsightsResponse(
        period_id=period_id,
        previous_period_id=prev_period.id,
        insights=insights,
        summary=summary,
    )


def _fmt_ars(n: float) -> str:
    return f"${n:,.0f}".replace(",", ".")


# ── Card Statement Import ────────────────────────────────────────────────────

# Keyword-based subcategory guessing
_SUBCATEGORY_KEYWORDS = {
    "indumentaria": ["zara", "h&m", "nike", "adidas", "rapsodia", "kosiuko", "levis", "uniqlo", "forever", "ropa", "indumentaria", "asos", "shein", "mango"],
    "supermercado": ["carrefour", "coto", "disco", "jumbo", "super", "vea", "changomas", "walmart"],
    "restaurantes": ["restaurant", "pizz", "burger", "mcdon", "starbucks", "cafe", "bar ", "sushi", "rappi", "pedidosya", "ifood", "resto"],
    "entretenimiento": ["spotify", "netflix", "disney", "hbo", "amazon prime", "steam", "playstation", "xbox", "cine", "teatro", "entrad"],
    "salud": ["farmacia", "farmacity", "medic", "doctor", "salud", "osde", "swiss", "galeno", "hospital", "optic"],
    "transporte": ["uber", "cabify", "ypf", "shell", "axion", "peaje", "estacion", "nafta", "combusti", "sube"],
    "hogar": ["easy", "sodimac", "mueble", "decoracion", "ferret", "limpieza", "hogar"],
    "tecnologia": ["mercadolibre", "apple", "samsung", "comput", "notebook", "celular", "tecno", "garbarino", "fravega", "musimundo"],
    "educacion": ["udemy", "coursera", "libro", "educacion", "universidad", "escuela", "curso"],
    "viajes": ["booking", "airbnb", "despegar", "hotel", "vuelo", "aerolinea", "avion", "latam", "flybondi"],
}


def _guess_subcategory(description: str) -> str:
    desc_lower = description.lower()
    for subcat, keywords in _SUBCATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                return subcat
    return "otros"


def _parse_statement_line(line: str) -> StatementLinePreview | None:
    """Try to parse a single line from a credit card statement.

    Supports common formats:
      - "DESCRIPCION    $1.234,56" or "$1234.56"
      - "DESCRIPCION    1.234,56" or "1234.56"
      - "15/03  DESCRIPCION  $1.234,56"
      - "DESCRIPCION  15/03/2026  1.234,56"
      - Tab or multiple-space separated
    """
    line = line.strip()
    if not line:
        return None

    # Try to find a monetary amount at the end of the line
    # Argentine format: $1.234.567,89 or 1.234,56
    # Also handle: $1234.56 or 1234.56
    patterns = [
        # Argentine: $1.234.567,89 or 1.234.567,89
        r'[\$]?\s*([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})\s*$',
        # Simple: $1234.56 or 1234.56
        r'[\$]?\s*([\d]+\.[\d]{2})\s*$',
        # Just a number: $123456 or 123456
        r'[\$]?\s*([\d]+)\s*$',
    ]

    amount = None
    desc_part = line

    for pat in patterns:
        m = re.search(pat, line)
        if m:
            amount_str = m.group(1)
            desc_part = line[:m.start()].strip()
            # Parse argentine format (dots as thousands, comma as decimal)
            if ',' in amount_str and '.' in amount_str:
                amount = float(amount_str.replace('.', '').replace(',', '.'))
            elif ',' in amount_str:
                amount = float(amount_str.replace(',', '.'))
            else:
                amount = float(amount_str)
            break

    if amount is None or amount <= 0:
        return None

    # Detect installment patterns BEFORE cleaning dates
    # Patterns: "C 03/05", "CUOTA 3/6", "CTA 2/12", "03/05 C", "(3/5)"
    # Also bare "NN/NN" where second number is <= 48 (likely cuota, not date)
    installment_current = None
    installment_total = None
    cuota_patterns = [
        r'(?:cuota|cta|c)\s*(\d{1,2})\s*/\s*(\d{1,2})',   # C 03/05, CUOTA 3/6, CTA 2/12
        r'(\d{1,2})\s*/\s*(\d{1,2})\s*(?:cuota|cta|c)\b',  # 03/05 C
        r'\((\d{1,2})/(\d{1,2})\)',                          # (3/5)
        r'\b(\d{2})/(\d{2})\b',                              # bare 06/06 (cuota if curr <= total <= 48)
    ]
    for cpat in cuota_patterns:
        cm = re.search(cpat, desc_part, re.IGNORECASE)
        if cm:
            curr = int(cm.group(1))
            total = int(cm.group(2))
            if 1 <= curr <= total <= 48:
                installment_current = curr
                installment_total = total
                desc_part = desc_part[:cm.start()] + desc_part[cm.end():]
                break

    # Clean up description: remove remaining date patterns like 15/03 or 15/03/2026
    desc_clean = re.sub(r'\d{2}/\d{2}(/\d{2,4})?\s*', '', desc_part).strip()
    # Remove trailing separators
    desc_clean = desc_clean.rstrip('-–—').strip()
    # Remove multiple spaces
    desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()

    if not desc_clean:
        desc_clean = "Consumo tarjeta"

    return StatementLinePreview(
        description=desc_clean,
        amount=amount,
        subcategory=_guess_subcategory(desc_clean),
        date="",
        installment_current=installment_current,
        installment_total=installment_total,
    )


@router.post("/statement/parse", response_model=StatementParseResponse)
def parse_statement(data: StatementParseRequest, db: Session = Depends(get_db)):
    """Parse pasted credit card statement text into structured lines."""
    # Load existing card transactions to flag duplicates
    existing_txns = db.query(Transaction).filter(
        Transaction.period_id == data.period_id,
        Transaction.category == "tarjeta",
    ).all()

    lines = data.text.strip().split('\n')
    parsed = []
    for line in lines:
        result = _parse_statement_line(line)
        if result:
            result.already_exists = _find_duplicate(existing_txns, result)
            parsed.append(result)
    return StatementParseResponse(
        lines=parsed,
        total=sum(l.amount for l in parsed),
        count=len(parsed),
    )


@router.post("/statement/import", status_code=201)
def import_statement(data: StatementImportRequest, db: Session = Depends(get_db)):
    """Import parsed statement lines as transactions.

    Lines with installment info (cuotas) create a CardPurchase and
    auto-generate remaining future installment transactions.
    Detects pre-loaded cuotas and skips duplicates.
    """
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == data.period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")

    # Load existing card transactions for this period to detect duplicates
    existing_txns = db.query(Transaction).filter(
        Transaction.period_id == data.period_id,
        Transaction.category == "tarjeta",
    ).all()

    created = 0
    skipped = 0
    cuotas_created = 0
    txn_date = date(period.year, period.month, 1)

    for line in data.lines:
        line_date = date.fromisoformat(line.date) if line.date else txn_date

        # Check for duplicate: same base description + similar amount already exists
        is_duplicate = _find_duplicate(existing_txns, line)
        if is_duplicate:
            skipped += 1
            continue

        if line.installment_current and line.installment_total and line.installment_total > 1:
            # This is a cuota — create CardPurchase + future installments
            total_amount = line.amount * line.installment_total
            installment_amount = line.amount

            purchase = CardPurchase(
                description=line.description,
                total_amount=total_amount,
                installments_total=line.installment_total,
                installment_amount=installment_amount,
                subcategory=line.subcategory,
                date=line_date,
                source_period_id=period.id,
            )
            db.add(purchase)
            db.flush()

            # Create transactions from current installment to the last one
            y, m = period.year, period.month
            for i in range(line.installment_current, line.installment_total + 1):
                target_period = get_or_create_period(db, y, m, period)
                txn = Transaction(
                    period_id=target_period.id,
                    description=f"{line.description} (cuota {i}/{line.installment_total})",
                    amount=installment_amount,
                    currency="ARS",
                    transaction_type="expense",
                    category="tarjeta",
                    subcategory=line.subcategory,
                    date=date(y, m, 1),
                    is_fixed=False,
                    notes="Importado desde resumen de tarjeta",
                    card_purchase_id=purchase.id,
                    installment_number=i,
                    credit_card_id=data.credit_card_id,
                )
                db.add(txn)
                created += 1
                y, m = _next_month(y, m)
            cuotas_created += 1
        else:
            # Simple one-time charge
            txn = Transaction(
                period_id=data.period_id,
                description=line.description,
                amount=line.amount,
                currency="ARS",
                transaction_type="expense",
                category="tarjeta",
                subcategory=line.subcategory,
                date=line_date,
                is_fixed=False,
                notes="Importado desde resumen de tarjeta",
                credit_card_id=data.credit_card_id,
            )
            db.add(txn)
            created += 1

    db.commit()
    msg = f"Se importaron {created} consumos de tarjeta"
    if cuotas_created > 0:
        msg += f" ({cuotas_created} en cuotas con cuotas futuras pre-cargadas)"
    if skipped > 0:
        msg += f". Se omitieron {skipped} que ya estaban cargados"
    return {"message": msg, "count": created, "skipped": skipped, "installment_purchases": cuotas_created}


def _find_duplicate(existing_txns: list, line: StatementLinePreview) -> bool:
    """Check if a statement line matches an already-existing transaction."""
    desc_lower = line.description.lower().strip()
    for txn in existing_txns:
        txn_desc = txn.description.lower().strip()
        # Check amount match (within 1 peso tolerance for rounding)
        if abs(txn.amount - line.amount) > 1:
            continue
        # Exact description match
        if txn_desc == desc_lower:
            return True
        # Pre-loaded cuota: "ZARA (cuota 4/6)" matches imported "ZARA"
        if desc_lower in txn_desc and txn.card_purchase_id is not None:
            return True
        # Imported description contained in existing (e.g. partial match)
        if txn_desc in desc_lower:
            return True
    return False


# ── Credit Cards ─────────────────────────────────────────────────────────────


@router.get("/credit-cards", response_model=list[CreditCardResponse])
def list_credit_cards(db: Session = Depends(get_db)):
    return db.query(CreditCard).order_by(CreditCard.name).all()


@router.post("/credit-cards", response_model=CreditCardResponse, status_code=201)
def create_credit_card(data: CreditCardCreate, db: Session = Depends(get_db)):
    existing = db.query(CreditCard).filter(CreditCard.name == data.name).first()
    if existing:
        raise HTTPException(400, f"Ya existe una tarjeta con el nombre '{data.name}'")
    card = CreditCard(**data.model_dump())
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.delete("/credit-cards/{card_id}", status_code=204)
def delete_credit_card(card_id: int, db: Session = Depends(get_db)):
    card = db.query(CreditCard).filter(CreditCard.id == card_id).first()
    if not card:
        raise HTTPException(404, "Tarjeta no encontrada")
    # Unlink transactions but don't delete them
    db.query(Transaction).filter(Transaction.credit_card_id == card_id).update(
        {Transaction.credit_card_id: None}
    )
    db.delete(card)
    db.commit()


# ── Natural Language Parser ──────────────────────────────────────────────────

_INCOME_KEYWORDS = [
    "ingres", "cobro", "recib", "salario", "sueldo", "gananci", "honorari",
]
_EXPENSE_KEYWORDS = [
    "pago", "gasto", "debo", "cuesta", "pongo", "abono", "cuota",
]

# Map description patterns to categories
_NL_CATEGORY_MAP = [
    (["alquiler", "alquilo"], "rent", "Alquiler"),
    (["expensas de cochera", "expensa cochera", "cochera"], "expensas_cochera", "Expensas cochera"),
    (["expensas", "expensa"], "expensas", "Expensas"),
    (["maestri", "universidad", "posgrado", "master"], "maestria", "Maestria"),
    (["epec", "luz", "electricidad", "energia"], "epec", "EPEC"),
    (["fondo comun", "fondo pareja", "fondo compartido"], "fondo_pareja", "Fondo comun pareja"),
    (["jubilacion", "retiro", "retirement", "fondo jubilacion"], "fondo_jubilacion", "Fondo jubilacion"),
    (["tarjeta", "tc", "credito"], "tarjeta", "Tarjeta de credito"),
]


def _parse_nl_amount(text: str) -> list[tuple[float, str, int, int]]:
    """Extract all amounts from text. Returns (amount, currency, start, end)."""
    results = []
    # Match patterns like: $1,750 usd, $400.000 ars, $915.000, US$100, u$s 100
    patterns = [
        # US$1,750 or US$ 1,750 or u$s 100 or USD 1750
        r'(?:us\$|u\$s|usd)\s*([\d.,]+)',
        # $1,750 usd or $400.000 ars
        r'\$([\d.,]+)\s*(usd|ars|dolares|pesos)',
        # Plain $amount (default ARS)
        r'\$([\d.,]+)',
        # Number + currency word
        r'([\d.,]+)\s*(usd|ars|dolares|pesos|dolar)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            amount_str = m.group(1)
            # Determine currency
            full = m.group(0).lower()
            currency = "USD" if any(w in full for w in ["usd", "us$", "u$s", "dolar"]) else "ARS"
            # If has group 2, check it
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                g2 = m.group(2).lower()
                if g2 in ("usd", "dolares", "dolar"):
                    currency = "USD"
                elif g2 in ("ars", "pesos"):
                    currency = "ARS"
            # Parse the number
            # Handle "1,750" (english) vs "400.000" (spanish) vs "1.750,50"
            if ',' in amount_str and '.' in amount_str:
                # Could be 1,750.00 (english) or 1.750,00 (spanish)
                if amount_str.rindex(',') > amount_str.rindex('.'):
                    # Spanish: 1.750,00
                    amount = float(amount_str.replace('.', '').replace(',', '.'))
                else:
                    # English: 1,750.00
                    amount = float(amount_str.replace(',', ''))
            elif ',' in amount_str:
                # Could be 1,750 (english thousands) or 3,50 (spanish decimal)
                parts = amount_str.split(',')
                if len(parts[-1]) == 3:
                    # English thousands: 1,750
                    amount = float(amount_str.replace(',', ''))
                else:
                    # Spanish decimal: 3,50
                    amount = float(amount_str.replace(',', '.'))
            elif '.' in amount_str:
                # Could be 400.000 (spanish thousands) or 3.50 (english decimal)
                parts = amount_str.split('.')
                if len(parts[-1]) == 3 and len(parts) > 1:
                    # Spanish thousands: 400.000
                    amount = float(amount_str.replace('.', ''))
                else:
                    amount = float(amount_str)
            else:
                amount = float(amount_str)

            if amount > 0:
                results.append((amount, currency, m.start(), m.end()))

    # Deduplicate overlapping matches (keep longest)
    results.sort(key=lambda x: (x[2], -(x[3] - x[2])))
    deduped = []
    last_end = -1
    for r in results:
        if r[2] >= last_end:
            deduped.append(r)
            last_end = r[3]
    return deduped


@router.post("/nl-parse", response_model=NLParseResponse)
def parse_natural_language(data: NLParseRequest, db: Session = Depends(get_db)):
    """Parse a free-text financial description into structured transactions."""
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == data.period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")

    text = data.text.strip()
    items = []

    # Split by sentence-ending periods (not decimal dots), +, ademas, tambien, se suman
    # Don't split on bare "y" as it often connects related amounts
    segments = re.split(r'(?<!\d)\.(?:\s|$)|\+|\bademas\b|\btambien\b|\bse suman\b', text, flags=re.IGNORECASE)

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        amounts = _parse_nl_amount(segment)
        if not amounts:
            continue

        seg_lower = segment.lower()

        # Determine if income or expense
        is_income = any(kw in seg_lower for kw in _INCOME_KEYWORDS)
        is_expense = any(kw in seg_lower for kw in _EXPENSE_KEYWORDS)

        for amount, currency, _, _ in amounts:
            # Try to match a category
            matched_cat = None
            matched_desc = None
            for keywords, cat_key, cat_desc in _NL_CATEGORY_MAP:
                if any(kw in seg_lower for kw in keywords):
                    matched_cat = cat_key
                    matched_desc = cat_desc
                    break

            # If no category matched, guess from context
            if not matched_cat:
                if is_income:
                    matched_cat = "salary_usd" if currency == "USD" else "salary_ars"
                    matched_desc = "Salario USD" if currency == "USD" else "Salario ARS"
                else:
                    matched_cat = "other_expense"
                    # Try to extract a meaningful description
                    matched_desc = segment[:60].strip()

            # Determine type
            if matched_cat in ("salary_usd", "salary_ars", "other_income"):
                txn_type = "income"
            elif is_income and not is_expense:
                txn_type = "income"
            else:
                txn_type = "expense"

            items.append(NLParseItem(
                description=matched_desc,
                amount=amount,
                currency=currency,
                transaction_type=txn_type,
                category=matched_cat,
                is_fixed=matched_cat not in ("other_expense", "other_income", "tarjeta"),
            ))

    return NLParseResponse(items=items, count=len(items))


@router.post("/nl-import", status_code=201)
def import_natural_language(data: dict, db: Session = Depends(get_db)):
    """Import parsed NL items as transactions."""
    period_id = data.get("period_id")
    items = data.get("items", [])
    period = db.query(MonthlyPeriod).filter(MonthlyPeriod.id == period_id).first()
    if not period:
        raise HTTPException(404, "Period not found")

    created = 0
    for item in items:
        txn = Transaction(
            period_id=period_id,
            description=item["description"],
            amount=item["amount"],
            currency=item["currency"],
            transaction_type=item["transaction_type"],
            category=item["category"],
            date=date(period.year, period.month, 1),
            is_fixed=item.get("is_fixed", False),
            notes="Importado desde texto libre",
        )
        db.add(txn)
        created += 1

    db.commit()
    return {"message": f"Se cargaron {created} movimientos", "count": created}
