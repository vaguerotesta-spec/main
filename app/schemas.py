from pydantic import BaseModel
from datetime import date
from typing import Optional


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
    transaction_type: str  # income / expense
    category: str
    date: date = None
    is_fixed: bool = False
    notes: str = ""


class TransactionUpdate(BaseModel):
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    transaction_type: Optional[str] = None
    category: Optional[str] = None
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
    date: date
    is_fixed: bool
    notes: str

    class Config:
        from_attributes = True


class MonthlySummary(BaseModel):
    period: MonthlyPeriodResponse
    total_income_ars: float
    total_income_usd: float
    total_income_ars_converted: float  # All income in ARS using blue rate
    total_expenses_ars: float
    total_expenses_usd: float
    total_expenses_ars_converted: float  # All expenses in ARS
    balance_ars: float
    transactions: list[TransactionResponse]
