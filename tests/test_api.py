import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# Use in-memory SQLite for tests with shared connection
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    # Import models to ensure they're registered with Base
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def create_test_period(rate=1350.0):
    return client.post("/api/periods", json={
        "year": 2026, "month": 4, "blue_dollar_rate": rate, "notes": ""
    })


class TestPeriods:
    def test_create_period(self):
        res = create_test_period()
        assert res.status_code == 201
        data = res.json()
        assert data["year"] == 2026
        assert data["month"] == 4
        assert data["blue_dollar_rate"] == 1350.0

    def test_duplicate_period(self):
        create_test_period()
        res = create_test_period()
        assert res.status_code == 400

    def test_list_periods(self):
        create_test_period()
        res = client.get("/api/periods")
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_update_period(self):
        pid = create_test_period().json()["id"]
        res = client.patch(f"/api/periods/{pid}", json={"blue_dollar_rate": 1400.0})
        assert res.status_code == 200
        assert res.json()["blue_dollar_rate"] == 1400.0

    def test_delete_period(self):
        pid = create_test_period().json()["id"]
        res = client.delete(f"/api/periods/{pid}")
        assert res.status_code == 204
        assert len(client.get("/api/periods").json()) == 0


class TestTransactions:
    def test_create_transaction(self):
        pid = create_test_period().json()["id"]
        res = client.post("/api/transactions", json={
            "period_id": pid, "description": "Alquiler",
            "amount": 915000, "currency": "ARS",
            "transaction_type": "expense", "category": "rent",
            "is_fixed": True, "notes": ""
        })
        assert res.status_code == 201
        assert res.json()["amount"] == 915000

    def test_list_transactions_by_period(self):
        pid = create_test_period().json()["id"]
        client.post("/api/transactions", json={
            "period_id": pid, "description": "Test",
            "amount": 100, "currency": "ARS",
            "transaction_type": "expense", "category": "other_expense",
            "notes": ""
        })
        res = client.get(f"/api/transactions?period_id={pid}")
        assert len(res.json()) == 1

    def test_delete_transaction(self):
        pid = create_test_period().json()["id"]
        tid = client.post("/api/transactions", json={
            "period_id": pid, "description": "Test",
            "amount": 100, "currency": "ARS",
            "transaction_type": "expense", "category": "other_expense",
            "notes": ""
        }).json()["id"]
        res = client.delete(f"/api/transactions/{tid}")
        assert res.status_code == 204


class TestSummary:
    def test_monthly_summary(self):
        pid = create_test_period(rate=1350.0).json()["id"]
        # Income
        client.post("/api/transactions", json={
            "period_id": pid, "description": "Salario USD",
            "amount": 1750, "currency": "USD",
            "transaction_type": "income", "category": "salary_usd",
            "notes": ""
        })
        client.post("/api/transactions", json={
            "period_id": pid, "description": "Salario ARS",
            "amount": 400000, "currency": "ARS",
            "transaction_type": "income", "category": "salary_ars",
            "notes": ""
        })
        # Expense
        client.post("/api/transactions", json={
            "period_id": pid, "description": "Alquiler",
            "amount": 915000, "currency": "ARS",
            "transaction_type": "expense", "category": "rent",
            "notes": ""
        })
        res = client.get(f"/api/summary/{pid}")
        assert res.status_code == 200
        data = res.json()
        assert data["total_income_usd"] == 1750
        assert data["total_income_ars"] == 400000
        assert data["total_income_ars_converted"] == 400000 + (1750 * 1350)
        assert data["total_expenses_ars"] == 915000
        assert data["balance_ars"] == (400000 + 1750 * 1350) - 915000


class TestSeedDefaults:
    def test_seed_creates_defaults(self):
        pid = create_test_period().json()["id"]
        res = client.post(f"/api/periods/{pid}/seed-defaults")
        assert res.status_code == 201
        data = res.json()
        assert data["message"].startswith("Created 9")
        txns = client.get(f"/api/transactions?period_id={pid}").json()
        assert len(txns) == 9


class TestCategories:
    def test_list_categories(self):
        res = client.get("/api/categories")
        assert res.status_code == 200
        data = res.json()
        assert "rent" in data
        assert data["rent"] == "Alquiler"


class TestDashboard:
    def test_dashboard_returns_html(self):
        res = client.get("/")
        assert res.status_code == 200
        assert "Mi Finanzas" in res.text
