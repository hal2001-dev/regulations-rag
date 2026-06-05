from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from apps.config import get_settings
from apps.routers import admin, authority, documents, ingest, jobs, query
from packages.code.logger import get_logger
from packages.db.connection import Base, get_engine

log = get_logger("apps.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = get_engine()

    log.info("Connecting to Postgres + creating tables (lifespan start)…")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    Base.metadata.create_all(engine)
    log.info(
        "Postgres ready. Qdrant URL: {url}, collection: {col}",
        url=settings.qdrant_url,
        col=settings.qdrant_collection,
    )

    yield

    log.info("Shutting down — disposing engine…")
    engine.dispose()


app = FastAPI(
    title="regulations-rag",
    version="0.1.0",
    description="사내 규정/매뉴얼/FAQ 한국어 RAG (LangGraph + Qdrant + Postgres)",
    lifespan=lifespan,
)


_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        log.warning("DB health check failed: {e}", e=e)
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "unreachable",
        "service": "regulations-rag",
        "version": app.version,
    }


app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(documents.router)
app.include_router(authority.router)
app.include_router(jobs.router)
app.include_router(admin.router)
