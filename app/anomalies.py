from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import avg_conversion_last_n_days, fetch_events
from app.metrics import compute_metrics
from app.models import AnomaliesResponse, AnomalyItem
from app.sessions import today_window, window_for_store


def detect_anomalies(store_id: str, now: datetime | None = None) -> AnomaliesResponse:
    start, end = window_for_store(store_id)
    ref = now or datetime.now(timezone.utc)
    metrics = compute_metrics(store_id)
    events = fetch_events(store_id, start, end, customer_only=True)

    anomalies: list[AnomalyItem] = []

    if metrics.queue_depth >= 5:
        anomalies.append(
            AnomalyItem(
                type="BILLING_QUEUE_SPIKE",
                severity="WARN" if metrics.queue_depth < 8 else "CRITICAL",
                message=f"Billing queue depth is {metrics.queue_depth}",
                suggested_action="Open additional billing counter or deploy floor staff to queue.",
                detected_at=ref,
            )
        )

    baseline = avg_conversion_last_n_days(store_id, metrics.date, days=7)
    if baseline is not None and metrics.unique_visitors >= 5:
        drop = baseline - metrics.conversion_rate
        if drop >= 0.15:
            anomalies.append(
                AnomalyItem(
                    type="CONVERSION_DROP",
                    severity="WARN" if drop < 0.25 else "CRITICAL",
                    message=(
                        f"Conversion {metrics.conversion_rate:.2%} vs "
                        f"7-day avg {baseline:.2%}"
                    ),
                    suggested_action="Review staffing, promotions, and stock-outs in high-dwell zones.",
                    detected_at=ref,
                )
            )

    if events:
        last_zone_event = max(
            (e for e in events if e.get("zone_id")),
            key=lambda e: e["timestamp"],
            default=None,
        )
        if last_zone_event:
            lag = ref - last_zone_event["timestamp"]
            if lag >= timedelta(minutes=30):
                zone = last_zone_event.get("zone_id", "unknown")
                anomalies.append(
                    AnomalyItem(
                        type="DEAD_ZONE",
                        severity="INFO",
                        message=f"No zone visits in {zone} for {int(lag.total_seconds() // 60)} minutes",
                        suggested_action="Verify camera coverage and merchandising in the quiet zone.",
                        detected_at=ref,
                    )
                )
    elif metrics.unique_visitors == 0:
        anomalies.append(
            AnomalyItem(
                type="DEAD_ZONE",
                severity="INFO",
                message="No customer traffic recorded today",
                suggested_action="Confirm store is open and detection pipeline is running.",
                detected_at=ref,
            )
        )

    stale_minutes = settings.stale_feed_minutes
    if events:
        last_ts = max(e["timestamp"] for e in events)
        if ref - last_ts > timedelta(minutes=stale_minutes):
            anomalies.append(
                AnomalyItem(
                    type="STALE_FEED",
                    severity="CRITICAL",
                    message=f"Last event older than {stale_minutes} minutes",
                    suggested_action="Restart detection workers and verify camera ingest.",
                    detected_at=ref,
                )
            )

    return AnomaliesResponse(store_id=store_id, anomalies=anomalies)
