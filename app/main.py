import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError

from app.database import engine, Base
from app.routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

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
