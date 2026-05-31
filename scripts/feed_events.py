#!/usr/bin/env python3
"""Batch-ingest JSONL events into the Store Intelligence API."""

import argparse
import json
import os
import time
from pathlib import Path

import httpx

BATCH_SIZE = 500


def feed(file_path: Path, api_url: str, realtime: bool = False, delay: float = 0.05) -> None:
    events: list[dict] = []
    with file_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    client = httpx.Client(base_url=api_url, timeout=30.0)
    for start in range(0, len(events), BATCH_SIZE):
        batch = events[start : start + BATCH_SIZE]
        response = client.post("/events/ingest", json={"events": batch})
        response.raise_for_status()
        body = response.json()
        print(
            f"ingested batch {start // BATCH_SIZE + 1}: "
            f"accepted={body['accepted']} dup={body['duplicates']} rej={body['rejected']}"
        )
        if realtime:
            time.sleep(delay * len(batch))
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="data/output/events.jsonl")
    parser.add_argument("--api-url", default=os.getenv("STORE_INTEL_API", "http://127.0.0.1:8000"))
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--delay", type=float, default=0.02)
    args = parser.parse_args()
    feed(Path(args.file), args.api_url, realtime=args.realtime, delay=args.delay)


if __name__ == "__main__":
    main()
