import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("store_intel.access")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        request.state.trace_id = trace_id
        store_id = request.path_params.get("id") or request.query_params.get("store_id")
        start = time.perf_counter()
        status_code = 500
        event_count = None

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Trace-Id"] = trace_id
            return response
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            if request.url.path.endswith("/events/ingest") and hasattr(request.state, "event_count"):
                event_count = request.state.event_count
            logger.info(
                "request_completed",
                extra={
                    "trace_id": trace_id,
                    "store_id": store_id,
                    "endpoint": request.url.path,
                    "latency_ms": latency_ms,
                    "event_count": event_count,
                    "status_code": status_code,
                },
            )
