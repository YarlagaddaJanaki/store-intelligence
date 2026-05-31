#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"

echo "[pipeline] Processing CCTV clips..."
python -m pipeline.detect --data-dir data --clips-dir data/clips --output data/output/events.jsonl "$@"

echo "[pipeline] Feeding API (if running)..."
if [ -f data/output/events.jsonl ]; then
  python scripts/feed_events.py --file data/output/events.jsonl || true
fi
echo "[pipeline] Done. Events at data/output/events.jsonl"
