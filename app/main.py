"""Gold API — a self-hosted, Railway-ready market-data service.

Pulls gold spot, USD/INR reference FX, daily gold bars, and (optionally) macro
and news context on a schedule, then serves the assembled snapshot over a small
read-only JSON API that any downstream app can consume.

Endpoints
---------
GET  /                        service metadata + endpoint index
GET  /health                  liveness + freshness (Railway healthcheck)
GET  /api/v1/snapshot         the full assembled payload (everything)
GET  /api/v1/gold             gold spot (USD/oz, USD/g) + derived INR/gram
GET  /api/v1/fx               USD/INR reference rate
GET  /api/v1/bars             daily gold bars
GET  /api/v1/macro            optional FRED series
GET  /api/v1/news             optional dated news context
GET  /api/v1/providers        per-provider health
POST /api/v1/refresh          force a refresh (bearer token if ADMIN_TOKEN set)
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import Settings
from .refresh import RefreshEngine
from .store import SnapshotStore

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger("gold_api")

settings = Settings.from_env()
store = SnapshotStore(state_path=settings.data_path / "published" / "snapshot.v1.json")
store.load()
engine = RefreshEngine(settings, store)

REFRESH_LOCK = asyncio.Lock()
STOP = asyncio.Event()


async def _scheduler() -> None:
    """Refresh immediately on boot, then every refresh_interval_seconds."""
    while not STOP.is_set():
        try:
            await asyncio.to_thread(engine.refresh_all)
        except Exception:  # pragma: no cover - defensive: never kill the loop
            LOGGER.exception("refresh cycle failed")
        try:
            await asyncio.wait_for(STOP.wait(), timeout=max(5, settings.refresh_interval_seconds))
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    LOGGER.info("starting %s v%s (refresh=%ss)", settings.service_name, settings.engine_version, settings.refresh_interval_seconds)
    task = asyncio.create_task(_scheduler())
    try:
        yield
    finally:
        STOP.set()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # pragma: no cover
            pass


app = FastAPI(
    title="Gold API",
    description="Self-hosted gold + FX + context data service. Refreshes every 60 seconds.",
    version=settings.engine_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _section(name: str) -> dict:
    value = store.section(name)
    if value is None:
        raise HTTPException(status_code=503, detail=f"section '{name}' is not ready yet")
    return value


@app.get("/")
async def root() -> dict:
    return {
        "service": settings.service_name,
        "engine_version": settings.engine_version,
        "schema_version": settings.schema_version,
        "refresh_interval_seconds": settings.refresh_interval_seconds,
        "endpoints": {
            "snapshot": "/api/v1/snapshot",
            "gold": "/api/v1/gold",
            "fx": "/api/v1/fx",
            "bars": "/api/v1/bars",
            "macro": "/api/v1/macro",
            "news": "/api/v1/news",
            "providers": "/api/v1/providers",
            "health": "/health",
            "refresh": "POST /api/v1/refresh",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health() -> dict:
    meta = store.meta()
    ready = bool(meta["sections"])
    return {
        "status": "ok" if ready else "starting",
        "service": settings.service_name,
        "engine_version": settings.engine_version,
        "sections_ready": meta["sections"],
        "last_cycle_at_utc": meta["last_cycle_at_utc"],
        "cycle_count": meta["cycle_count"],
    }


@app.get("/api/v1/snapshot")
async def snapshot() -> JSONResponse:
    payload = engine.build_snapshot()
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/v1/gold")
async def gold() -> dict:
    payload = engine.build_snapshot()
    return {
        "generated_at_utc": payload["generated_at_utc"],
        "gold": payload["sections"]["gold"],
        "derived": payload["derived"],
    }


@app.get("/api/v1/fx")
async def fx() -> dict:
    return _section("fx")


@app.get("/api/v1/bars")
async def bars() -> dict:
    return _section("bars")


@app.get("/api/v1/macro")
async def macro() -> dict:
    return _section("macro")


@app.get("/api/v1/news")
async def news() -> dict:
    return _section("news")


@app.get("/api/v1/providers")
async def providers() -> dict:
    return {"providers": store.providers()}


@app.post("/api/v1/refresh")
async def refresh(request: Request, authorization: str | None = Header(default=None)) -> dict:
    if settings.admin_token:
        supplied = authorization or ""
        expected = f"Bearer {settings.admin_token}"
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="valid bearer token required")
    async with REFRESH_LOCK:
        await asyncio.to_thread(engine.refresh_all, force=True)
    return {"status": "refreshed", "meta": store.meta()}
