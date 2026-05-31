from collections import defaultdict
from datetime import datetime, timezone

from app.database import fetch_events, upsert_baseline
from app.models import StoreMetricsResponse, ZoneMetric
from app.sessions import (
    build_sessions,
    correlate_conversions,
    load_pos_transactions,
    today_window,
    window_for_store,
)


def compute_metrics(store_id: str, day: datetime | None = None) -> StoreMetricsResponse:
    start, end = today_window(day) if day else window_for_store(store_id)
    events = fetch_events(store_id, start, end, customer_only=True)
    sessions = build_sessions(events)
    transactions = load_pos_transactions(store_id)
    converted = correlate_conversions(sessions, transactions)

    unique_visitors = len(sessions)
    conversion_rate = (len(converted) / unique_visitors) if unique_visitors else 0.0

    dwell_accum: dict[str, list[int]] = defaultdict(list)
    for session in sessions.values():
        for zone, dwells in session["dwell_by_zone"].items():
            dwell_accum[zone].extend(dwells)

    avg_dwell_per_zone = [
        ZoneMetric(
            zone_id=zone,
            avg_dwell_ms=(sum(values) / len(values)) if values else 0.0,
            visit_count=len(values),
        )
        for zone, values in sorted(dwell_accum.items())
    ]

    queue_depth = 0
    for event in reversed(events):
        if event["event_type"] == "BILLING_QUEUE_JOIN":
            meta = event.get("metadata") or {}
            if meta.get("queue_depth") is not None:
                queue_depth = int(meta["queue_depth"])
                break

    billing_sessions = sum(1 for s in sessions.values() if s["billing_visited"])
    abandons = sum(s["abandons"] for s in sessions.values())
    abandonment_rate = (abandons / billing_sessions) if billing_sessions else 0.0

    metric_date = start.date().isoformat()
    upsert_baseline(store_id, metric_date, conversion_rate)

    return StoreMetricsResponse(
        store_id=store_id,
        date=metric_date,
        unique_visitors=unique_visitors,
        conversion_rate=round(conversion_rate, 4),
        avg_dwell_per_zone=avg_dwell_per_zone,
        queue_depth=queue_depth,
        abandonment_rate=round(abandonment_rate, 4),
    )
