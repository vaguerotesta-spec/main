from pydantic import BaseModel
from datetime import date
from typing import Optional, Union


class MonthlyPeriodCreate(BaseModel):
    year: int
    month: int
    blue_dollar_rate: float
    notes: str = ""


class MonthlyPeriodUpdate(BaseModel):
    blue_dollar_rate: Optional[float] = None
    notes: Optional[str] = None


class MonthlyPeriodResponse(BaseModel):
    id: int
    year: int
    month: int
    blue_dollar_rate: float
    notes: str

    class Config:
        from_attributes = True


class TransactionCreate(BaseModel):
    period_id: int
    description: str
    amount: float
    currency: str = "ARS"
    transaction_type: str
    category: str
    subcategory: Optional[str] = None
    date: Union[date, None] = None
    is_fixed: bool = False
    notes: str = ""
    card_purchase_id: Optional[int] = None
    installment_number: Optional[int] = None


class TransactionUpdate(BaseModel):
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    transaction_type: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    date: Optional[date] = None
    is_fixed: Optional[bool] = None
    notes: Optional[str] = None


class TransactionResponse(BaseModel):
    id: int
    period_id: int
    description: str
    amount: float
    currency: str
    transaction_type: str
    category: str
    subcategory: Optional[str]
    date: date
    is_fixed: bool
    notes: str
    card_purchase_id: Optional[int]
    installment_number: Optional[int]

    class Config:
        from_attributes = True


class MonthlySummary(BaseModel):
    period: MonthlyPeriodResponse
    total_income_ars: float
    total_income_usd: float
    total_income_ars_converted: float
    total_expenses_ars: float
    total_expenses_usd: float
    total_expenses_ars_converted: float
    balance_ars: float
    transactions: list[TransactionResponse]


# ── Card Purchases ───────────────────────────────────────


class CardPurchaseCreate(BaseModel):
    description: str
    total_amount: float
    installments_total: int
    installment_current: int
    subcategory: str = "otros"
    period_id: int
    date: Union[date, None] = None


class CardPurchaseResponse(BaseModel):
    id: int
    description: str
    total_amount: float
    installments_total: int
    installment_amount: float
    subcategory: str
    date: date
    source_period_id: int

    class Config:
        from_attributes = True


# ── Insights ─────────────────────────────────────────────


class InsightItem(BaseModel):
    category: str
    message: str
    change_percent: Optional[float] = None
    direction: str  # "up", "down", "stable", "new"


class PeriodInsightsResponse(BaseModel):
    period_id: int
    previous_period_id: Optional[int]
    insights: list[InsightItem]
    summary: str
