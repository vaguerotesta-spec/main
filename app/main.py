from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.database import engine, Base
from app.routes import router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Mi Finanzas", version="1.0.0")
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    with open("app/templates/dashboard.html", "r") as f:
        return HTMLResponse(content=f.read())
