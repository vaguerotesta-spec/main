from pydantic import BaseModel, field_validator
from datetime import date, datetime
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
    date: str = ""
    is_fixed: bool = False
    notes: str = ""
    card_purchase_id: Optional[int] = None
    installment_number: Optional[int] = None
    credit_card_id: Optional[int] = None

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if not v or v == "":
            return ""
        if isinstance(v, date):
            return v.isoformat()
        return str(v)


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
    credit_card_id: Optional[int] = None


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
    credit_card_id: Optional[int]

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
    date: str = ""
    credit_card_id: Optional[int] = None

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if not v or v == "" or v is None:
            return ""
        if isinstance(v, date):
            return v.isoformat()
        return str(v)


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


# ── Credit Cards ─────────────────────────────────────────


class CreditCardCreate(BaseModel):
    name: str
    color: str = "#B07A7A"


class CreditCardResponse(BaseModel):
    id: int
    name: str
    color: str

    class Config:
        from_attributes = True


# ── Insights ─────────────────────────────────────────────


class InsightItem(BaseModel):
    category: str
    message: str
    change_percent: Optional[float] = None
    direction: str


class PeriodInsightsResponse(BaseModel):
    period_id: int
    previous_period_id: Optional[int]
    insights: list[InsightItem]
    summary: str


# ── Card Statement Import ────────────────────────────────


class StatementLinePreview(BaseModel):
    description: str
    amount: float
    subcategory: str
    date: str
    installment_current: Optional[int] = None
    installment_total: Optional[int] = None


class StatementParseRequest(BaseModel):
    period_id: int
    text: str


class StatementParseResponse(BaseModel):
    lines: list[StatementLinePreview]
    total: float
    count: int


class StatementImportRequest(BaseModel):
    period_id: int
    lines: list[StatementLinePreview]
    credit_card_id: Optional[int] = None


# ── Natural Language Parser ──────────────────────────────


class NLParseItem(BaseModel):
    description: str
    amount: float
    currency: str
    transaction_type: str  # income / expense
    category: str
    is_fixed: bool


class NLParseRequest(BaseModel):
    period_id: int
    text: str


class NLParseResponse(BaseModel):
    items: list[NLParseItem]
    count: int
