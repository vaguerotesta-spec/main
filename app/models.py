from sqlalchemy import Column, Integer, Float, String, Date, Boolean
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


class CardSubcategory(str, enum.Enum):
    INDUMENTARIA = "indumentaria"
    SUPERMERCADO = "supermercado"
    RESTAURANTES = "restaurantes"
    ENTRETENIMIENTO = "entretenimiento"
    SALUD = "salud"
    TRANSPORTE = "transporte"
    HOGAR = "hogar"
    TECNOLOGIA = "tecnologia"
    EDUCACION = "educacion"
    VIAJES = "viajes"
    OTROS = "otros"


CARD_SUBCATEGORY_LABELS = {
    "indumentaria": "Indumentaria",
    "supermercado": "Supermercado",
    "restaurantes": "Restaurantes",
    "entretenimiento": "Entretenimiento",
    "salud": "Salud",
    "transporte": "Transporte",
    "hogar": "Hogar",
    "tecnologia": "Tecnología",
    "educacion": "Educación",
    "viajes": "Viajes",
    "otros": "Otros",
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
    transaction_type = Column(String, nullable=False)
    category = Column(String, nullable=False)
    subcategory = Column(String, nullable=True, default=None)
    date = Column(Date, default=date.today)
    is_fixed = Column(Boolean, default=False)
    notes = Column(String, default="")
    card_purchase_id = Column(Integer, nullable=True, default=None)
    installment_number = Column(Integer, nullable=True, default=None)
    credit_card_id = Column(Integer, nullable=True, default=None)
    import_batch_id = Column(String, nullable=True, default=None)


class CardPurchase(Base):
    __tablename__ = "card_purchases"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, nullable=False)
    total_amount = Column(Float, nullable=False)
    installments_total = Column(Integer, nullable=False)
    installment_amount = Column(Float, nullable=False)
    subcategory = Column(String, nullable=True, default="otros")
    date = Column(Date, default=date.today)
    source_period_id = Column(Integer, nullable=False)


class CustomSubcategory(Base):
    __tablename__ = "custom_subcategories"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True)
    label = Column(String, nullable=False)


class CustomCategory(Base):
    __tablename__ = "custom_categories"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True)
    label = Column(String, nullable=False)
    category_type = Column(String, nullable=False, default="expense")  # income / expense


class CreditCard(Base):
    __tablename__ = "credit_cards"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)  # e.g. "Visa Galicia"
    color = Column(String, default="#B07A7A")  # display color
