from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.database import get_db
from app.models import (
    MonthlyPeriod,
    Transaction,
    CardPurchase,
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
    InsightItem,
    PeriodInsightsResponse,
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
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(txn, key, value)
    db.commit()
    db.refresh(txn)
    return txn


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


@router.get("/categories")
def list_categories():
    return CATEGORY_LABELS


@router.get("/card-subcategories")
def list_card_subcategories():
    return CARD_SUBCATEGORY_LABELS


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
