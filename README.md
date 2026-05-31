# Store Intelligence — Apex Retail Hiring Challenge

End-to-end pipeline: **CCTV → detection events → REST API → live metrics**.

## Quick start (5 commands)

```bash
git clone <your-repo-url> store-intelligence && cd store-intelligence
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
docker compose up -d --build
python scripts/generate_sample_events.py && python -m pipeline.detect --replay-sample
python scripts/feed_events.py --file data/output/events.jsonl
curl http://127.0.0.1:8000/stores/STORE_BLR_002/metrics
```

## Dataset setup

1. Unzip the challenge archive into `data/`:
   - `data/clips/<store>/<camera>.mp4`
   - Replace `data/store_layout.json`, `data/pos_transactions.csv`, `data/sample_events.jsonl` if provided versions differ
2. Run detection:

```bash
# Linux/macOS
bash pipeline/run.sh

# Windows
powershell -File pipeline/run.ps1
```

Output: `data/output/events.jsonl` (or per-camera files under `data/output/`).

### Without GPU / footage

```bash
python scripts/generate_sample_events.py
python -m pipeline.detect --replay-sample
```

## Feed events into API

```bash
python scripts/feed_events.py --file data/output/events.jsonl
# Simulated real-time (Part E dashboard):
python scripts/feed_events.py --file data/output/events.jsonl --realtime &
python dashboard/live_dashboard.py
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/events/ingest` | Batch ingest (max 500), idempotent by `event_id` |
| GET | `/stores/{id}/metrics` | Visitors, conversion, dwell, queue, abandonment |
| GET | `/stores/{id}/funnel` | Entry → Zone → Billing → Purchase |
| GET | `/stores/{id}/heatmap` | Zone frequency 0–100 + dwell |
| GET | `/stores/{id}/anomalies` | Queue spike, conversion drop, dead zone |
| GET | `/health` | Service + per-store freshness |

Interactive docs: http://127.0.0.1:8000/docs

## Live dashboard (bonus)

Terminal UI polling metrics:

```bash
set STORE_INTEL_API=http://127.0.0.1:8000
python dashboard/live_dashboard.py
```

## Tests

```bash
pytest --cov=app --cov=pipeline --cov-report=term-missing
python assertions.py   # requires API on :8000
```

## Project layout

```
store-intelligence/
├── pipeline/          # detect.py, tracker.py, emit.py
├── app/               # FastAPI intelligence API
├── tests/             # pytest + PROMPT blocks
├── docs/              # DESIGN.md, CHOICES.md
├── dashboard/         # live terminal dashboard
├── data/              # clips, layout, POS, events
├── docker-compose.yml
└── README.md
```

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md) — architecture and AI-assisted decisions
- [docs/CHOICES.md](docs/CHOICES.md) — model, schema, API rationale

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `STORE_INTEL_API` | `http://127.0.0.1:8000` | Feed script / dashboard target |
| `STORE_INTEL_DATABASE_URL` | `sqlite:///./data/store_intel.db` | API database |
| `STORE_ID` | `STORE_BLR_002` | Dashboard store |

## Submission checklist

- [ ] `docker compose up` works on a clean machine
- [ ] Pipeline README steps produce `data/output/events.jsonl`
- [ ] `DESIGN.md` and `CHOICES.md` reviewed
- [ ] Prompt blocks present atop each file in `tests/`
- [ ] Private repo invite sent to reviewer
