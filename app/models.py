from sqlalchemy import Column, Integer, Float, String, Date, Boolean, Enum as SAEnum
from datetime import date
import enum

from app.database import Base


class Currency(str, enum.Enum):
    USD = "USD"
    ARS = "ARS"


class TransactionType(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"


class Category(str, enum.Enum):
    # Income
    SALARY_USD = "salary_usd"
    SALARY_ARS = "salary_ars"
    OTHER_INCOME = "other_income"
    # Fixed expenses
    RENT = "rent"
    EXPENSAS = "expensas"
    EXPENSAS_COCHERA = "expensas_cochera"
    MAESTRIA = "maestria"
    EPEC = "epec"
    FONDO_PAREJA = "fondo_pareja"
    FONDO_JUBILACION = "fondo_jubilacion"
    TARJETA = "tarjeta"
    # Variable
    OTHER_EXPENSE = "other_expense"


CATEGORY_LABELS = {
    "salary_usd": "Salario USD",
    "salary_ars": "Salario ARS",
    "other_income": "Otro ingreso",
    "rent": "Alquiler",
    "expensas": "Expensas",
    "expensas_cochera": "Expensas cochera",
    "maestria": "Maestría",
    "epec": "EPEC",
    "fondo_pareja": "Fondo común pareja",
    "fondo_jubilacion": "Fondo jubilación",
    "tarjeta": "Tarjeta de crédito",
    "other_expense": "Otro gasto",
}


class MonthlyPeriod(Base):
    __tablename__ = "monthly_periods"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    blue_dollar_rate = Column(Float, nullable=False, default=1350.0)
    notes = Column(String, default="")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    period_id = Column(Integer, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="ARS")
    transaction_type = Column(String, nullable=False)  # income / expense
    category = Column(String, nullable=False)
    date = Column(Date, default=date.today)
    is_fixed = Column(Boolean, default=False)
    notes = Column(String, default="")
