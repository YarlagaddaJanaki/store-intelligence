# Store Intelligence — Architecture

## Overview

This system turns anonymised retail CCTV into actionable offline conversion analytics for Apex Retail. The pipeline has four stages: **detection** (people, zones, staff), **event emission** (schema-compliant JSONL), **ingestion API** (real-time metrics and anomalies), and an optional **live dashboard** that proves end-to-end connectivity.

The north-star metric is **offline conversion rate**: purchasers divided by unique visitor sessions, with staff excluded and re-entries deduplicated at the session layer.

```
CCTV clips → detect.py (YOLOv8 + tracker) → events.jsonl
      → POST /events/ingest → SQLite → GET /metrics, /funnel, /heatmap, /anomalies
      → dashboard/live_dashboard.py (Rich terminal UI)
```

## Detection Layer

`pipeline/detect.py` reads each clip referenced in `data/store_layout.json`. For every frame (sampled with `--stride` to balance speed and accuracy):

1. **YOLOv8n** detects persons (COCO class 0).
2. **CentroidTracker** (`pipeline/tracker.py`) maintains track IDs and assigns a `visitor_id` per visit. Recent exit positions are stored for **re-ID** within a 30-second window to emit `REENTRY` instead of a duplicate `ENTRY`.
3. **Entry line crossing** (`pipeline/zones.py`) classifies inbound vs outbound on the entry camera.
4. **Zone polygons** (normalised coordinates) map floor/billing cameras to `SKINCARE`, `MOISTURISER`, `BILLING`, etc.
5. **Staff heuristic** inspects upper-body HSV saturation/brightness (uniform-like colours). Staff events are still emitted with `is_staff=true` but excluded downstream.
6. **Dwell events** fire every 30 seconds of continuous zone occupancy.
7. **Billing queue** events set `metadata.queue_depth` from concurrent non-staff tracks in the billing polygon.

If challenge footage is missing, the pipeline replays `data/sample_events.jsonl` so the API and tests remain runnable.

## Event Stream

Events are newline-delimited JSON matching the challenge schema. `pipeline/emit.py` assigns UUID `event_id`s, ISO-8601 UTC timestamps from clip start + frame offset, and monotonic `metadata.session_seq` per visitor.

Design choices supporting analytics:

- Low-confidence detections are **not dropped**; confidence is preserved for calibration review.
- `zone_id` is null only for pure entry/exit/re-entry lines.
- POS correlation happens in the API, not the detector, keeping the pipeline camera-agnostic.

## Intelligence API

FastAPI application (`app/`) backed by **SQLite** for simplicity and single-container deployment.

| Module | Responsibility |
|--------|----------------|
| `ingestion.py` | Validates with Pydantic, idempotent insert on `event_id`, partial batch errors |
| `sessions.py` | Rebuilds per-visitor sessions; POS window matching (5 min before txn) |
| `metrics.py` | Unique visitors, conversion, dwell, queue depth, abandonment |
| `funnel.py` | Session funnel with drop-off percentages |
| `heatmap.py` | Zone frequency normalised 0–100; `data_confidence` if &lt;20 sessions |
| `anomalies.py` | Queue spike, conversion drop vs 7-day baseline, dead zone, stale feed |
| `health.py` | Per-store last event + `STALE_FEED` if lag &gt;10 minutes |

**Structured logging** (`middleware.py`) emits `trace_id`, `store_id`, `endpoint`, `latency_ms`, `event_count`, `status_code` per request.

**Graceful degradation**: `/internal/db-down` marks DB unavailable; all read/write routes return HTTP 503 with a structured JSON body (no stack traces).

## Deployment

`docker compose up` builds the API image, mounts `data/`, and exposes port 8000. The detection pipeline runs on the host (GPU optional) and feeds events via `scripts/feed_events.py`.

## Live Dashboard (Part E)

`dashboard/live_dashboard.py` uses Rich to poll `GET /stores/{id}/metrics` every two seconds while `feed_events.py --realtime` streams events — demonstrating a live path without batch-only processing.

## AI-Assisted Decisions

1. **Tracker vs DeepSORT** — An LLM suggested DeepSORT + OSNet for re-entry accuracy. I overrode with a centroid tracker plus exit-position memory because 15fps blurred CCTV and a 48-hour window made heavy Re-ID slow to iterate; the compromise still emits explicit `REENTRY` events and documents where full Re-ID would help (similar apparel, fast re-entry).

2. **Staff detection** — AI proposed a VLM clip classifier. I disagreed for latency/cost and implemented HSV uniform heuristics first, with VLM as a documented upgrade path in `CHOICES.md`.

3. **SQLite vs Postgres** — AI recommended Postgres for 40 stores. I agreed for production but chose SQLite for the submission acceptance gate (zero external services in `docker compose up`), with schema isolated so migration is straightforward.

## Security & Operations

- No PII in events; faces are pre-blurred in source footage.
- Idempotent ingest supports at-least-once delivery from the pipeline.
- Health endpoint is the on-call entry point for stale cameras or stopped workers.

## Extending to 40 Stores

First bottlenecks at scale: SQLite write contention on ingest (move to Postgres + partitioned tables), synchronous metric recompute per request (add materialised views or stream processor), and single-process detection (horizontally shard by `store_id` with a message bus).
