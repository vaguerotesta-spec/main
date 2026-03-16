import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

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
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def create_test_period(rate=1350.0, year=2026, month=4):
    return client.post("/api/periods", json={
        "year": year, "month": month, "blue_dollar_rate": rate, "notes": ""
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

    def test_create_transaction_with_subcategory(self):
        pid = create_test_period().json()["id"]
        res = client.post("/api/transactions", json={
            "period_id": pid, "description": "Zara",
            "amount": 50000, "currency": "ARS",
            "transaction_type": "expense", "category": "tarjeta",
            "subcategory": "indumentaria", "notes": ""
        })
        assert res.status_code == 201
        assert res.json()["subcategory"] == "indumentaria"

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


    def test_delete_all_card_transactions(self):
        pid = create_test_period().json()["id"]
        # Create 2 card txns and 1 non-card txn
        client.post("/api/transactions", json={
            "period_id": pid, "description": "Zara", "amount": 50000,
            "currency": "ARS", "transaction_type": "expense",
            "category": "tarjeta", "notes": ""
        })
        client.post("/api/transactions", json={
            "period_id": pid, "description": "Spotify", "amount": 2500,
            "currency": "ARS", "transaction_type": "expense",
            "category": "tarjeta", "notes": ""
        })
        client.post("/api/transactions", json={
            "period_id": pid, "description": "Alquiler", "amount": 915000,
            "currency": "ARS", "transaction_type": "expense",
            "category": "rent", "notes": ""
        })
        res = client.delete(f"/api/transactions/card-bulk/{pid}")
        assert res.status_code == 200
        assert res.json()["count"] == 2
        # Only the non-card txn should remain
        txns = client.get(f"/api/transactions?period_id={pid}").json()
        assert len(txns) == 1
        assert txns[0]["category"] == "rent"


class TestSummary:
    def test_monthly_summary(self):
        pid = create_test_period(rate=1350.0).json()["id"]
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

    def test_list_card_subcategories(self):
        res = client.get("/api/card-subcategories")
        assert res.status_code == 200
        data = res.json()
        assert "indumentaria" in data
        assert data["indumentaria"] == "Indumentaria"


class TestCustomSubcategories:
    def test_create_custom_subcategory(self):
        res = client.post("/api/card-subcategories", json={"key": "mascotas", "label": "Mascotas"})
        assert res.status_code == 201
        data = res.json()
        assert "mascotas" in data
        assert data["mascotas"] == "Mascotas"

    def test_list_includes_custom(self):
        client.post("/api/card-subcategories", json={"key": "gym", "label": "Gimnasio"})
        res = client.get("/api/card-subcategories")
        data = res.json()
        assert "gym" in data
        assert "indumentaria" in data  # default still there

    def test_delete_custom_subcategory(self):
        client.post("/api/card-subcategories", json={"key": "test_cat", "label": "Test"})
        res = client.delete("/api/card-subcategories/test_cat")
        assert res.status_code == 200
        assert "test_cat" not in res.json()

    def test_cannot_delete_default(self):
        res = client.delete("/api/card-subcategories/indumentaria")
        assert res.status_code == 400

    def test_duplicate_rejected(self):
        client.post("/api/card-subcategories", json={"key": "mascotas", "label": "Mascotas"})
        res = client.post("/api/card-subcategories", json={"key": "mascotas", "label": "Mascotas 2"})
        assert res.status_code == 400


class TestCardPurchases:
    def test_create_card_purchase_creates_installments(self):
        pid = create_test_period(year=2026, month=4).json()["id"]
        res = client.post("/api/card-purchases", json={
            "description": "Zapatillas",
            "total_amount": 300000,
            "installments_total": 6,
            "installment_current": 4,
            "subcategory": "indumentaria",
            "period_id": pid,
        })
        assert res.status_code == 201
        data = res.json()
        assert data["installment_amount"] == 50000
        assert data["installments_total"] == 6

        # Should create 3 transactions (cuotas 4, 5, 6)
        txns = client.get(f"/api/transactions?period_id={pid}").json()
        assert len(txns) == 1  # cuota 4 in April
        assert "cuota 4/6" in txns[0]["description"]
        assert txns[0]["subcategory"] == "indumentaria"
        assert txns[0]["installment_number"] == 4

        # May and June periods should have been created
        periods = client.get("/api/periods").json()
        assert len(periods) == 3  # April, May, June

    def test_card_purchase_amounts(self):
        pid = create_test_period(year=2026, month=3).json()["id"]
        client.post("/api/card-purchases", json={
            "description": "TV",
            "total_amount": 600000,
            "installments_total": 3,
            "installment_current": 1,
            "subcategory": "tecnologia",
            "period_id": pid,
        })
        # 3 installments of 200000 in March, April, May
        periods = client.get("/api/periods").json()
        assert len(periods) == 3

        for p in periods:
            txns = client.get(f"/api/transactions?period_id={p['id']}").json()
            assert len(txns) == 1
            assert txns[0]["amount"] == 200000

    def test_card_purchase_year_rollover(self):
        pid = create_test_period(year=2026, month=11).json()["id"]
        client.post("/api/card-purchases", json={
            "description": "Viaje",
            "total_amount": 900000,
            "installments_total": 3,
            "installment_current": 1,
            "subcategory": "viajes",
            "period_id": pid,
        })
        periods = client.get("/api/periods").json()
        year_months = sorted([(p["year"], p["month"]) for p in periods])
        assert (2026, 11) in year_months
        assert (2026, 12) in year_months
        assert (2027, 1) in year_months

    def test_delete_card_purchase_removes_transactions(self):
        pid = create_test_period(year=2026, month=6).json()["id"]
        res = client.post("/api/card-purchases", json={
            "description": "Compra",
            "total_amount": 150000,
            "installments_total": 3,
            "installment_current": 1,
            "subcategory": "otros",
            "period_id": pid,
        })
        purchase_id = res.json()["id"]
        client.delete(f"/api/card-purchases/{purchase_id}")
        txns = client.get("/api/transactions").json()
        assert len(txns) == 0

    def test_invalid_installment_current(self):
        pid = create_test_period().json()["id"]
        res = client.post("/api/card-purchases", json={
            "description": "Test",
            "total_amount": 100000,
            "installments_total": 3,
            "installment_current": 5,
            "subcategory": "otros",
            "period_id": pid,
        })
        assert res.status_code == 400


class TestInsights:
    def test_insights_no_previous_period(self):
        pid = create_test_period(year=2026, month=4).json()["id"]
        client.post("/api/transactions", json={
            "period_id": pid, "description": "Salario",
            "amount": 400000, "currency": "ARS",
            "transaction_type": "income", "category": "salary_ars",
            "notes": ""
        })
        res = client.get(f"/api/insights/{pid}")
        assert res.status_code == 200
        data = res.json()
        assert data["previous_period_id"] is None
        assert "primer mes" in data["summary"]

    def test_insights_compares_two_periods(self):
        # March
        p1 = create_test_period(year=2026, month=3).json()["id"]
        client.post("/api/transactions", json={
            "period_id": p1, "description": "Alquiler",
            "amount": 800000, "currency": "ARS",
            "transaction_type": "expense", "category": "rent",
            "notes": ""
        })
        client.post("/api/transactions", json={
            "period_id": p1, "description": "Salario",
            "amount": 400000, "currency": "ARS",
            "transaction_type": "income", "category": "salary_ars",
            "notes": ""
        })
        # April (expenses went up)
        p2 = create_test_period(year=2026, month=4).json()["id"]
        client.post("/api/transactions", json={
            "period_id": p2, "description": "Alquiler",
            "amount": 915000, "currency": "ARS",
            "transaction_type": "expense", "category": "rent",
            "notes": ""
        })
        client.post("/api/transactions", json={
            "period_id": p2, "description": "Salario",
            "amount": 400000, "currency": "ARS",
            "transaction_type": "income", "category": "salary_ars",
            "notes": ""
        })
        res = client.get(f"/api/insights/{p2}")
        assert res.status_code == 200
        data = res.json()
        assert data["previous_period_id"] == p1
        assert len(data["insights"]) > 0
        # Should mention expenses went up
        msgs = [i["message"] for i in data["insights"]]
        assert any("subieron" in m for m in msgs)

    def test_insights_card_subcategory(self):
        p1 = create_test_period(year=2026, month=3).json()["id"]
        client.post("/api/transactions", json={
            "period_id": p1, "description": "Zara",
            "amount": 50000, "currency": "ARS",
            "transaction_type": "expense", "category": "tarjeta",
            "subcategory": "indumentaria", "notes": ""
        })
        p2 = create_test_period(year=2026, month=4).json()["id"]
        client.post("/api/transactions", json={
            "period_id": p2, "description": "Zara + H&M",
            "amount": 80000, "currency": "ARS",
            "transaction_type": "expense", "category": "tarjeta",
            "subcategory": "indumentaria", "notes": ""
        })
        res = client.get(f"/api/insights/{p2}")
        data = res.json()
        msgs = [i["message"] for i in data["insights"]]
        assert any("Indumentaria" in m for m in msgs)

    def test_insights_new_category(self):
        p1 = create_test_period(year=2026, month=3).json()["id"]
        client.post("/api/transactions", json={
            "period_id": p1, "description": "Alquiler",
            "amount": 800000, "currency": "ARS",
            "transaction_type": "expense", "category": "rent",
            "notes": ""
        })
        p2 = create_test_period(year=2026, month=4).json()["id"]
        client.post("/api/transactions", json={
            "period_id": p2, "description": "EPEC",
            "amount": 55000, "currency": "ARS",
            "transaction_type": "expense", "category": "epec",
            "notes": ""
        })
        res = client.get(f"/api/insights/{p2}")
        data = res.json()
        msgs = [i["message"] for i in data["insights"]]
        assert any("EPEC" in m for m in msgs)


class TestStatementParse:
    def test_parse_argentine_format(self):
        pid = create_test_period().json()["id"]
        text = """SPOTIFY                    $2.500,00
MERCADOLIBRE               $45.000,00
ZARA                       $89.000,00"""
        res = client.post("/api/statement/parse", json={"period_id": pid, "text": text})
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == 3
        assert data["total"] == 2500 + 45000 + 89000
        # Check subcategory guessing
        descs = {l["description"]: l["subcategory"] for l in data["lines"]}
        assert descs["SPOTIFY"] == "entretenimiento"
        assert descs["MERCADOLIBRE"] == "tecnologia"
        assert descs["ZARA"] == "indumentaria"

    def test_parse_with_dates(self):
        pid = create_test_period().json()["id"]
        text = "15/03  CARREFOUR  $32.500,00"
        res = client.post("/api/statement/parse", json={"period_id": pid, "text": text})
        data = res.json()
        assert data["count"] == 1
        assert data["lines"][0]["amount"] == 32500
        assert data["lines"][0]["subcategory"] == "supermercado"

    def test_parse_empty_lines_skipped(self):
        pid = create_test_period().json()["id"]
        text = "\n\nSPOTIFY  $2.500,00\n\n"
        res = client.post("/api/statement/parse", json={"period_id": pid, "text": text})
        assert res.json()["count"] == 1

    def test_parse_no_matches(self):
        pid = create_test_period().json()["id"]
        res = client.post("/api/statement/parse", json={"period_id": pid, "text": "no numbers here"})
        assert res.json()["count"] == 0

    def test_parse_detects_cuotas(self):
        pid = create_test_period().json()["id"]
        text = """ZARA C 03/05                $25.000,00
NIKE CUOTA 2/6              $15.000,00
SAMSUNG (1/12)              $45.000,00"""
        res = client.post("/api/statement/parse", json={"period_id": pid, "text": text})
        data = res.json()
        assert data["count"] == 3
        lines = {l["description"]: l for l in data["lines"]}
        assert lines["ZARA"]["installment_current"] == 3
        assert lines["ZARA"]["installment_total"] == 5
        assert lines["NIKE"]["installment_current"] == 2
        assert lines["NIKE"]["installment_total"] == 6
        assert lines["SAMSUNG"]["installment_current"] == 1
        assert lines["SAMSUNG"]["installment_total"] == 12

    def test_parse_real_format_with_zeta(self):
        """Test with real Argentine card statement format."""
        pid = create_test_period().json()["id"]
        text = """MERPAGO*MERCADOLIBRE          06/06     $10.725,00
MERPAGO*MULHAUS               03/06     $22.533,33
RAPPI ARG CVV                           $9.990,00
ZETA ENE/26                   03/03     $98.941,06"""
        res = client.post("/api/statement/parse", json={"period_id": pid, "text": text})
        data = res.json()
        assert data["count"] == 4
        # MERPAGO*MERCADOLIBRE 06/06 should detect cuota 6/6
        meli = next(l for l in data["lines"] if "MERCADOLIBRE" in l["description"])
        assert meli["installment_current"] == 6
        assert meli["installment_total"] == 6


class TestStatementImport:
    def test_import_creates_transactions(self):
        pid = create_test_period().json()["id"]
        lines = [
            {"description": "SPOTIFY", "amount": 2500, "subcategory": "entretenimiento", "date": ""},
            {"description": "ZARA", "amount": 89000, "subcategory": "indumentaria", "date": ""},
        ]
        res = client.post("/api/statement/import", json={"period_id": pid, "lines": lines})
        assert res.status_code == 201
        assert res.json()["count"] == 2

        txns = client.get(f"/api/transactions?period_id={pid}").json()
        assert len(txns) == 2
        assert all(t["category"] == "tarjeta" for t in txns)
        assert all("Importado" in t["notes"] for t in txns)

    def test_import_cuotas_creates_future_installments(self):
        pid = create_test_period(year=2026, month=4).json()["id"]
        lines = [
            {"description": "ZARA", "amount": 25000, "subcategory": "indumentaria", "date": "",
             "installment_current": 3, "installment_total": 5},
            {"description": "SPOTIFY", "amount": 2500, "subcategory": "entretenimiento", "date": ""},
        ]
        res = client.post("/api/statement/import", json={"period_id": pid, "lines": lines})
        assert res.status_code == 201
        data = res.json()
        assert data["installment_purchases"] == 1
        # ZARA: cuotas 3,4,5 = 3 txns + SPOTIFY = 1 txn = 4 total
        assert data["count"] == 4

        # Check April has cuota 3 + spotify
        txns_april = client.get(f"/api/transactions?period_id={pid}").json()
        assert len(txns_april) == 2

        # May and June should have been created with cuotas 4 and 5
        periods = client.get("/api/periods").json()
        assert len(periods) == 3  # April, May, June


class TestCreditCards:
    def test_create_credit_card(self):
        res = client.post("/api/credit-cards", json={"name": "Visa Galicia", "color": "#3498db"})
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Visa Galicia"
        assert data["color"] == "#3498db"

    def test_list_credit_cards(self):
        client.post("/api/credit-cards", json={"name": "Visa Galicia"})
        client.post("/api/credit-cards", json={"name": "Mastercard BBVA"})
        res = client.get("/api/credit-cards")
        assert res.status_code == 200
        assert len(res.json()) == 2

    def test_duplicate_card_rejected(self):
        client.post("/api/credit-cards", json={"name": "Visa Galicia"})
        res = client.post("/api/credit-cards", json={"name": "Visa Galicia"})
        assert res.status_code == 400

    def test_delete_credit_card(self):
        card_id = client.post("/api/credit-cards", json={"name": "Test Card"}).json()["id"]
        res = client.delete(f"/api/credit-cards/{card_id}")
        assert res.status_code == 204
        assert len(client.get("/api/credit-cards").json()) == 0

    def test_delete_card_unlinks_transactions(self):
        pid = create_test_period().json()["id"]
        card_id = client.post("/api/credit-cards", json={"name": "Visa"}).json()["id"]
        client.post("/api/transactions", json={
            "period_id": pid, "description": "Zara",
            "amount": 50000, "currency": "ARS",
            "transaction_type": "expense", "category": "tarjeta",
            "credit_card_id": card_id, "notes": ""
        })
        client.delete(f"/api/credit-cards/{card_id}")
        txns = client.get(f"/api/transactions?period_id={pid}").json()
        assert len(txns) == 1
        assert txns[0]["credit_card_id"] is None

    def test_statement_import_with_credit_card(self):
        pid = create_test_period().json()["id"]
        card_id = client.post("/api/credit-cards", json={"name": "Visa Galicia"}).json()["id"]
        lines = [
            {"description": "SPOTIFY", "amount": 2500, "subcategory": "entretenimiento", "date": ""},
        ]
        res = client.post("/api/statement/import", json={
            "period_id": pid, "lines": lines, "credit_card_id": card_id
        })
        assert res.status_code == 201
        txns = client.get(f"/api/transactions?period_id={pid}").json()
        assert txns[0]["credit_card_id"] == card_id

    def test_card_purchase_with_credit_card(self):
        pid = create_test_period(year=2026, month=5).json()["id"]
        card_id = client.post("/api/credit-cards", json={"name": "MC BBVA"}).json()["id"]
        client.post("/api/card-purchases", json={
            "description": "Zapatillas", "total_amount": 300000,
            "installments_total": 3, "installment_current": 1,
            "subcategory": "indumentaria", "period_id": pid,
            "credit_card_id": card_id,
        })
        txns = client.get(f"/api/transactions?period_id={pid}").json()
        assert txns[0]["credit_card_id"] == card_id


class TestNLParser:
    def test_parse_basic_income_expense(self):
        pid = create_test_period().json()["id"]
        text = "Me ingresan $1,750 usd y $400.000 ars. Pago $915.000 de alquiler"
        res = client.post("/api/nl-parse", json={"period_id": pid, "text": text})
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 3
        descs = {i["description"]: i for i in data["items"]}
        # Should detect USD salary
        usd_items = [i for i in data["items"] if i["currency"] == "USD"]
        assert len(usd_items) >= 1
        assert usd_items[0]["amount"] == 1750
        # Should detect rent
        rent_items = [i for i in data["items"] if i["category"] == "rent"]
        assert len(rent_items) == 1
        assert rent_items[0]["amount"] == 915000

    def test_parse_multiple_expenses(self):
        pid = create_test_period().json()["id"]
        text = "$170.000 de expensas + $60.000 de cochera + $250.000 de la maestria"
        res = client.post("/api/nl-parse", json={"period_id": pid, "text": text})
        data = res.json()
        assert data["count"] == 3
        cats = [i["category"] for i in data["items"]]
        assert "expensas" in cats
        assert "expensas_cochera" in cats
        assert "maestria" in cats

    def test_import_nl_creates_transactions(self):
        pid = create_test_period().json()["id"]
        items = [
            {"description": "Salario USD", "amount": 1750, "currency": "USD",
             "transaction_type": "income", "category": "salary_usd", "is_fixed": True},
            {"description": "Alquiler", "amount": 915000, "currency": "ARS",
             "transaction_type": "expense", "category": "rent", "is_fixed": True},
        ]
        res = client.post("/api/nl-import", json={"period_id": pid, "items": items})
        assert res.status_code == 201
        assert res.json()["count"] == 2
        txns = client.get(f"/api/transactions?period_id={pid}").json()
        assert len(txns) == 2

    def test_parse_empty_text(self):
        pid = create_test_period().json()["id"]
        res = client.post("/api/nl-parse", json={"period_id": pid, "text": "nada de nada"})
        assert res.status_code == 200
        assert res.json()["count"] == 0


class TestDashboard:
    def test_dashboard_returns_html(self):
        res = client.get("/")
        assert res.status_code == 200
        assert "Mi Finanzas" in res.text
