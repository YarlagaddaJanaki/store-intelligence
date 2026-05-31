#!/usr/bin/env python3
"""Generate sample_events.jsonl for local dev when challenge ZIP is unavailable."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

STORE = "STORE_BLR_002"


def main() -> None:
    base = datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc)
    visitors = [
        ("VIS_a10001", False, ["ENTRY", "ZONE_ENTER", "ZONE_DWELL", "BILLING_QUEUE_JOIN"]),
        ("VIS_a10002", False, ["ENTRY", "ZONE_ENTER", "EXIT"]),
        ("VIS_staff01", True, ["ENTRY", "ZONE_ENTER", "ZONE_EXIT"]),
        ("VIS_a10003", False, ["ENTRY", "REENTRY", "ZONE_ENTER", "BILLING_QUEUE_JOIN"]),
    ]
    zones = {"ZONE_ENTER": "SKINCARE", "ZONE_DWELL": "SKINCARE", "BILLING_QUEUE_JOIN": "BILLING"}
    out = Path("data/sample_events.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    events = []
    offset_min = 0
    for visitor_id, is_staff, flow in visitors:
        seq = 0
        for step in flow:
            seq += 1
            ts = base + timedelta(minutes=offset_min, seconds=seq * 8)
            zone = zones.get(step)
            meta = {"session_seq": seq, "sku_zone": zone, "queue_depth": None}
            if step == "BILLING_QUEUE_JOIN":
                meta["queue_depth"] = 3
            events.append(
                {
                    "event_id": str(uuid.uuid4()),
                    "store_id": STORE,
                    "camera_id": "CAM_ENTRY_01" if step in ("ENTRY", "EXIT", "REENTRY") else "CAM_FLOOR_01",
                    "visitor_id": visitor_id,
                    "event_type": step,
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "zone_id": zone,
                    "dwell_ms": 32000 if step == "ZONE_DWELL" else 0,
                    "is_staff": is_staff,
                    "confidence": 0.55 if step == "ZONE_DWELL" else 0.88,
                    "metadata": meta,
                }
            )
        offset_min += 12

    with out.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    print(f"Wrote {len(events)} events to {out}")


if __name__ == "__main__":
    main()
