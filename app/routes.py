from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.database import get_db
from app.models import MonthlyPeriod, Transaction, CATEGORY_LABELS
from app.schemas import (
    MonthlyPeriodCreate,
    MonthlyPeriodUpdate,
    MonthlyPeriodResponse,
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    MonthlySummary,
)

router = APIRouter(prefix="/api")


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
    if dump["date"] is None:
        dump["date"] = date.today()
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
        # Income
        {"description": "Salario USD", "amount": 1750, "currency": "USD", "transaction_type": "income", "category": "salary_usd", "is_fixed": True},
        {"description": "Salario ARS", "amount": 400000, "currency": "ARS", "transaction_type": "income", "category": "salary_ars", "is_fixed": True},
        # Fixed expenses
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


@router.get("/categories")
def list_categories():
    return CATEGORY_LABELS
