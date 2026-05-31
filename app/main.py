import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.anomalies import detect_anomalies
from app.config import settings
from app.database import init_db, is_db_available, set_db_available
from app.funnel import compute_funnel
from app.health import build_health
from app.heatmap import compute_heatmap
from app.ingestion import ingest_events
from app.metrics import compute_metrics
from app.middleware import StructuredLoggingMiddleware
from app.models import ErrorResponse, IngestRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Store Intelligence API", version="1.0.0", lifespan=lifespan)
app.add_middleware(StructuredLoggingMiddleware)


def _error(request: Request, status: int, error: str, detail: str) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", None)
    body = ErrorResponse(error=error, detail=detail, trace_id=trace_id)
    return JSONResponse(status_code=status, content=body.model_dump())


def _db_guard(request: Request):
    if not is_db_available():
        return _error(request, 503, "service_unavailable", "database unavailable")
    return None


@app.post("/events/ingest")
async def post_events_ingest(request: Request, body: IngestRequest) -> Any:
    blocked = _db_guard(request)
    if blocked:
        return blocked
    try:
        request.state.event_count = len(body.events)
        result = ingest_events(body.events)
        return result
    except sqlite3.OperationalError:
        return _error(request, 503, "service_unavailable", "database unavailable")


@app.get("/stores/{store_id}/metrics")
async def get_store_metrics(store_id: str, request: Request) -> Any:
    blocked = _db_guard(request)
    if blocked:
        return blocked
    try:
        return compute_metrics(store_id)
    except sqlite3.OperationalError:
        return _error(request, 503, "service_unavailable", "database unavailable")


@app.get("/stores/{store_id}/funnel")
async def get_store_funnel(store_id: str, request: Request) -> Any:
    blocked = _db_guard(request)
    if blocked:
        return blocked
    try:
        return compute_funnel(store_id)
    except sqlite3.OperationalError:
        return _error(request, 503, "service_unavailable", "database unavailable")


@app.get("/stores/{store_id}/heatmap")
async def get_store_heatmap(store_id: str, request: Request) -> Any:
    blocked = _db_guard(request)
    if blocked:
        return blocked
    try:
        return compute_heatmap(store_id)
    except sqlite3.OperationalError:
        return _error(request, 503, "service_unavailable", "database unavailable")


@app.get("/stores/{store_id}/anomalies")
async def get_store_anomalies(store_id: str, request: Request) -> Any:
    blocked = _db_guard(request)
    if blocked:
        return blocked
    try:
        return detect_anomalies(store_id)
    except sqlite3.OperationalError:
        return _error(request, 503, "service_unavailable", "database unavailable")


@app.get("/health")
async def get_health(request: Request) -> Any:
    blocked = _db_guard(request)
    if blocked:
        return blocked
    try:
        return build_health()
    except sqlite3.OperationalError:
        return _error(request, 503, "service_unavailable", "database unavailable")


@app.get("/internal/db-down")
async def simulate_db_down() -> dict[str, str]:
    """Test-only hook to verify graceful degradation."""
    set_db_available(False)
    return {"status": "database marked unavailable"}


@app.get("/internal/db-up")
async def simulate_db_up() -> dict[str, str]:
    set_db_available(True)
    init_db()
    return {"status": "database restored"}
