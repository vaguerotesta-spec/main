import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text, inspect

from app.database import engine, Base
from app.routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

# Add new columns to existing databases
_new_columns = [
    ("transactions", "subcategory", "TEXT"),
    ("transactions", "card_purchase_id", "INTEGER"),
    ("transactions", "installment_number", "INTEGER"),
]
with engine.connect() as conn:
    inspector = inspect(engine)
    if inspector.has_table("transactions"):
        existing = {col["name"] for col in inspector.get_columns("transactions")}
        for table, col, col_type in _new_columns:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                logger.info(f"Added column {col} to {table}")
        conn.commit()

app = FastAPI(title="Mi Finanzas", version="1.0.0")
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": str(exc.errors())})


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    with open("app/templates/dashboard.html", "r") as f:
        return HTMLResponse(content=f.read())
