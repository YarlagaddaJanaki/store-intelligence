# Engineering Choices

This document records three deliberate decisions for the Apex Retail Store Intelligence challenge, including what AI tools suggested and what I chose.

---

## 1. Detection model: YOLOv8n + centroid tracking

### Options considered

| Option | Pros | Cons |
|--------|------|------|
| YOLOv8n + ByteTrack | Fast, strong MOT | Extra dependency tuning |
| RT-DETR | Accuracy on small objects | Heavier, slower on CPU |
| MediaPipe | Lightweight | Weaker in crowded billing |
| VLM per-frame labelling | Flexible semantics | Cost, latency, non-deterministic |

### What AI suggested

ChatGPT/Cursor recommended **YOLOv8medium + ByteTrack** for crowded entry groups and **GPT-4V** to label staff vs customer on a sparse frame sample.

### What I chose and why

**YOLOv8n** with a **custom CentroidTracker** and exit-position re-ID memory.

- **Speed**: Processing 20-minute 1080p clips per camera requires frame striding; nano weights keep iteration fast on a laptop GPU or CPU.
- **Groups**: YOLO still emits one box per person; the tracker assigns separate `visitor_id`s — addressing the “3 people = 3 ENTRY events” criterion.
- **Occlusion**: Low-confidence boxes are kept (`confidence` not clamped) so the API can measure calibration rather than silent drops.
- **Re-entry**: Exit centroid + time window reuses `visitor_id` and emits `REENTRY`; full OSNet would be the next step if false re-IDs appear in evaluation.

### VLM usage

I did **not** ship VLM staff detection in code. A trial prompt was: *“Does this bounding crop show retail staff uniform vs shopper?”* — it worked on clear vest frames but failed on lighting-matched customers. The HSV uniform heuristic is weaker but deterministic and testable; I would switch to a fine-tuned small classifier if ground truth labels were available.

---

## 2. Event schema design

### Options considered

- **Flat denormalised events** (chosen) — every row is self-contained for ingest idempotency.
- **Separate session table in the pipeline** — fewer events but harder to reprocess clips.
- **Protobuf stream** — efficient but poor fit for hiring JSON fixtures.

### What AI suggested

An LLM proposed adding `track_id` and `frame_number` top-level fields and bundling dwell into zone exit only.

### What I chose and why

Strict adherence to the **challenge schema** with rich `metadata` for extensibility (`queue_depth`, `sku_zone`, `session_seq`).

- **Idempotency**: `event_id` UUID at emission time lets ingest dedupe without semantic hashing.
- **Analytics**: `ZONE_DWELL` every 30s supports heatmap dwell; instantaneous types use `dwell_ms=0`.
- **Staff**: `is_staff` on every event so the API can filter without re-inferring.
- **POS correlation in API**: Keeps detection free of POS clock skew; conversion uses billing presence in a 5-minute pre-transaction window per the brief.

I rejected AI’s idea to drop low-confidence events — the brief explicitly scores calibration on retaining them.

---

## 3. API architecture: FastAPI + SQLite + session rebuild

### Options considered

- **FastAPI + SQLite** (chosen for submission)
- **FastAPI + Postgres + Redis cache**
- **ClickHouse for events + API aggregator**

### What AI suggested

Use **Postgres** with materialised views refreshed by triggers and **Redis** for `/metrics` caching.

### What I chose and why

**FastAPI** with synchronous SQLite writes and **in-request session aggregation** from stored events.

- **Acceptance gate**: `docker compose up` must work with only Docker — no second service.
- **Correctness first**: Funnel uses session reconstruction in Python (`app/sessions.py`) so re-entries do not double-count Entry stage.
- **7-day conversion baseline**: Stored in `daily_baselines` on each metrics call for anomaly `CONVERSION_DROP`.
- **503 path**: Global `is_db_available` flag for testable graceful degradation.

At 40 live stores, the first break would be ingest QPS on SQLite; migration path is Postgres + nightly baseline batch jobs while keeping the same REST contract.

---

## Summary

| Decision | Choice | AI override? |
|----------|--------|--------------|
| Detection | YOLOv8n + centroid/re-ID memory | Yes — skipped VLM staff |
| Schema | Challenge JSON + metadata | Yes — keep low confidence |
| API storage | SQLite, compute on read | Yes — defer Redis/Postgres for ops simplicity |
