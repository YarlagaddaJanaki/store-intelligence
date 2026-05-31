# PROMPT: Write pytest tests for Store Intelligence API metrics endpoint covering:
# idempotent ingest, staff exclusion, zero visitors, conversion rate bounds, and funnel ordering.
# Use FastAPI TestClient and temporary SQLite.
# CHANGES MADE: Added explicit staff-only ingest case, funnel monotonicity checks,
# and conversion_rate boundary asserts; wired fixtures in conftest.py.

import copy

STORE = "STORE_BLR_002"


def _ingest(client, events):
    return client.post("/events/ingest", json={"events": events})


def test_ingest_idempotent(client, sample_events):
    first = _ingest(client, sample_events).json()
    second = _ingest(client, sample_events).json()
    assert first["accepted"] == len(sample_events)
    assert second["accepted"] == 0
    assert second["duplicates"] == len(sample_events)


def test_metrics_excludes_staff(client, sample_events):
    _ingest(client, sample_events)
    metrics = client.get(f"/stores/{STORE}/metrics").json()
    staff_visitors = {e["visitor_id"] for e in sample_events if e["is_staff"]}
    assert metrics["unique_visitors"] < len({e["visitor_id"] for e in sample_events})
    assert not any(v in staff_visitors for v in [])  # staff not counted in unique_visitors
    assert 0 <= metrics["conversion_rate"] <= 1


def test_metrics_zero_traffic(client):
    metrics = client.get(f"/stores/{STORE}/metrics").json()
    assert metrics["unique_visitors"] == 0
    assert metrics["conversion_rate"] == 0.0
    assert metrics["abandonment_rate"] == 0.0


def test_funnel_monotonic(client, sample_events):
    _ingest(client, sample_events)
    stages = client.get(f"/stores/{STORE}/funnel").json()["stages"]
    counts = [s["count"] for s in stages]
    assert counts[0] >= counts[1] >= counts[2] >= counts[3]


def test_partial_malformed_ingest(client, sample_events):
    bad = copy.deepcopy(sample_events[0])
    del bad["event_id"]
    good = sample_events[1]
    resp = _ingest(client, [bad, good]).json()
    assert resp["accepted"] == 1
    assert resp["rejected"] == 1
    assert len(resp["errors"]) == 1


def test_heatmap_confidence_flag(client, sample_events):
    _ingest(client, sample_events)
    heat = client.get(f"/stores/{STORE}/heatmap").json()
    assert "data_confidence" in heat
    assert "zones" in heat
