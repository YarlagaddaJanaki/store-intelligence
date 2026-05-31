from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import last_event_timestamp, list_store_ids
from app.models import HealthResponse, StoreHealthItem


def build_health() -> HealthResponse:
    now = datetime.now(timezone.utc)
    stale_delta = timedelta(minutes=settings.stale_feed_minutes)
    warnings: list[str] = []
    stores: list[StoreHealthItem] = []

    store_ids = list_store_ids()
    if not store_ids:
        store_ids = ["STORE_BLR_002"]

    for store_id in store_ids:
        last_ts = last_event_timestamp(store_id)
        stale = last_ts is None or (now - last_ts) > stale_delta
        if stale:
            warnings.append(f"STALE_FEED:{store_id}")
        stores.append(
            StoreHealthItem(store_id=store_id, last_event_at=last_ts, stale=stale)
        )

    status = "degraded" if warnings else "ok"
    return HealthResponse(status=status, stores=stores, warnings=warnings)
