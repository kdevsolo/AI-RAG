import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import document_routes, user_routes
from app.core.config import config
from app.db.session import engine
from app.temporal.client import connect as connect_temporal

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Connected once here, not per request — see app/temporal/client.py.
    # Non-fatal if Temporal isn't up: the app still serves everything that
    # doesn't touch it (uploads will fail until it's reachable).
    if await connect_temporal() is None:
        logger.warning(
            "Could not connect to Temporal at %s — document uploads will fail "
            "until it's reachable (make temporal-up).",
            config.temporal_host,
        )
    yield


app = FastAPI(title=config.app_name, version=config.app_version, lifespan=lifespan)


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
app.include_router(document_routes.router, prefix="/api/v1")
