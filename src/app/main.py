from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import user_routes
from app.core.config import config
from app.db.session import engine

app = FastAPI(title=config.app_name, version=config.app_version)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    """Smoke test: can we actually open a connection to Postgres?"""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": "reachable"}


# Routers
app.include_router(user_routes.router, prefix="/api/v1")
