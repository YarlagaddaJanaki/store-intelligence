from datetime import datetime

from app.database import fetch_events
from app.models import FunnelResponse, FunnelStage
from app.sessions import (
    build_sessions,
    correlate_conversions,
    load_pos_transactions,
    today_window,
    window_for_store,
)


def compute_funnel(store_id: str, day: datetime | None = None) -> FunnelResponse:
    start, end = today_window(day) if day else window_for_store(store_id)
    events = fetch_events(store_id, start, end, customer_only=True)
    sessions = build_sessions(events)
    transactions = load_pos_transactions(store_id)
    converted = correlate_conversions(sessions, transactions)

    entry_count = len(sessions)
    zone_visit_count = sum(1 for s in sessions.values() if s["zones_visited"])
    billing_count = sum(1 for s in sessions.values() if s["billing_visited"])
    purchase_count = len(converted)

    counts = [entry_count, zone_visit_count, billing_count, purchase_count]
    stages: list[FunnelStage] = []
    labels = ["Entry", "Zone Visit", "Billing Queue", "Purchase"]

    for idx, label in enumerate(labels):
        count = counts[idx]
        drop_off = None
        if idx > 0 and counts[idx - 1] > 0:
            drop_off = round(100.0 * (1 - count / counts[idx - 1]), 2)
        stages.append(FunnelStage(stage=label, count=count, drop_off_pct=drop_off))

    return FunnelResponse(
        store_id=store_id,
        date=start.date().isoformat(),
        stages=stages,
    )
