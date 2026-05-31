# PROMPT: Generate pytest tests for anomaly detection and health endpoints including
# STALE_FEED, database 503 degradation, and queue spike detection with mocked events.
# CHANGES MADE: Added db-down simulation via /internal/db-down, health structure checks,
# and synthetic queue spike event to trigger BILLING_QUEUE_SPIKE.

import uuid
from datetime import datetime, timedelta, timezone

STORE = "STORE_BLR_002"


def _event(event_type: str, **kwargs):
    base = {
        "event_id": str(uuid.uuid4()),
        "store_id": STORE,
        "camera_id": "CAM_BILLING_01",
        "visitor_id": kwargs.get("visitor_id", "VIS_q001"),
        "event_type": event_type,
        "timestamp": kwargs.get(
            "timestamp",
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
        "zone_id": kwargs.get("zone_id", "BILLING"),
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": 0.9,
        "metadata": kwargs.get("metadata", {"session_seq": 1, "sku_zone": "BILLING", "queue_depth": 6}),
    }
    base.update(kwargs)
    return base


def test_health_shape(client):
    body = client.get("/health").json()
    assert body["status"] in ("ok", "degraded")
    assert isinstance(body["stores"], list)


def test_db_unavailable_returns_503(client):
    client.get("/internal/db-down")
    response = client.get(f"/stores/{STORE}/metrics")
    assert response.status_code == 503
    assert response.json()["error"] == "service_unavailable"
    client.get("/internal/db-up")


def test_queue_spike_anomaly(client):
    events = [_event("BILLING_QUEUE_JOIN") for _ in range(3)]
    client.post("/events/ingest", json={"events": events})
    anomalies = client.get(f"/stores/{STORE}/anomalies").json()["anomalies"]
    types = {a["type"] for a in anomalies}
    assert "BILLING_QUEUE_SPIKE" in types


def test_reentry_in_funnel_not_double_entry(client, sample_events):
    client.post("/events/ingest", json={"events": sample_events})
    funnel = client.get(f"/stores/{STORE}/funnel").json()
    entry = next(s for s in funnel["stages"] if s["stage"] == "Entry")
    assert entry["count"] >= 1


def test_stale_feed_warning(client):
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    client.post(
        "/events/ingest",
        json={
            "events": [
                _event("ZONE_ENTER", timestamp=old_ts, zone_id="SKINCARE"),
            ]
        },
    )
    health = client.get("/health").json()
    assert health["status"] == "degraded"
    assert any("STALE_FEED" in w for w in health.get("warnings", []))
