"""Session reconstruction from event streams."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings


def _parse_ts(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        ts = value
    else:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def build_sessions(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Map visitor_id -> session aggregate for the day window.
    Re-entry events attach to the same visitor_id without double-counting ENTRY.
    """
    by_visitor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_visitor[event["visitor_id"]].append(event)

    sessions: dict[str, dict[str, Any]] = {}
    for visitor_id, visitor_events in by_visitor.items():
        visitor_events.sort(key=lambda e: _parse_ts(e["timestamp"]))
        has_entry = any(e["event_type"] in ("ENTRY", "REENTRY") for e in visitor_events)
        if not has_entry:
            continue

        zones_visited: set[str] = set()
        billing_visited = False
        queue_joins = 0
        abandons = 0
        dwell_by_zone: dict[str, list[int]] = defaultdict(list)
        last_queue_depth = 0

        for event in visitor_events:
            et = event["event_type"]
            zone = event.get("zone_id")
            if et in ("ZONE_ENTER", "ZONE_DWELL") and zone:
                zones_visited.add(zone)
            if et == "ZONE_DWELL" and zone:
                dwell_by_zone[zone].append(event.get("dwell_ms", 0))
            if zone == "BILLING" or event.get("metadata", {}).get("sku_zone") == "BILLING":
                billing_visited = True
            if et == "BILLING_QUEUE_JOIN":
                billing_visited = True
                queue_joins += 1
                meta = event.get("metadata") or {}
                if meta.get("queue_depth") is not None:
                    last_queue_depth = int(meta["queue_depth"])
            if et == "BILLING_QUEUE_ABANDON":
                abandons += 1

        sessions[visitor_id] = {
            "visitor_id": visitor_id,
            "events": visitor_events,
            "zones_visited": zones_visited,
            "billing_visited": billing_visited,
            "queue_joins": queue_joins,
            "abandons": abandons,
            "last_queue_depth": last_queue_depth,
            "dwell_by_zone": dict(dwell_by_zone),
            "first_ts": _parse_ts(visitor_events[0]["timestamp"]),
            "last_ts": _parse_ts(visitor_events[-1]["timestamp"]),
        }
    return sessions


def load_pos_transactions(store_id: str) -> list[dict[str, Any]]:
    import csv
    from pathlib import Path

    path = Path(settings.pos_csv)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("store_id") != store_id:
                continue
            ts = _parse_ts(row["timestamp"])
            rows.append(
                {
                    "transaction_id": row["transaction_id"],
                    "timestamp": ts,
                    "basket_value_inr": float(row["basket_value_inr"]),
                }
            )
    return rows


def correlate_conversions(
    sessions: dict[str, dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> set[str]:
    """Visitors with billing presence in conversion window before a POS txn."""
    converted: set[str] = set()
    window = timedelta(minutes=settings.conversion_window_minutes)

    for visitor_id, session in sessions.items():
        if not session["billing_visited"]:
            continue
        billing_times = [
            _parse_ts(e["timestamp"])
            for e in session["events"]
            if e["event_type"] in ("BILLING_QUEUE_JOIN", "ZONE_ENTER", "ZONE_DWELL")
            and (e.get("zone_id") == "BILLING" or (e.get("metadata") or {}).get("sku_zone") == "BILLING")
        ]
        if not billing_times:
            billing_times = [session["last_ts"]]

        for txn in transactions:
            txn_ts = txn["timestamp"]
            for billing_ts in billing_times:
                if billing_ts <= txn_ts <= billing_ts + window:
                    converted.add(visitor_id)
                    break
    return converted


def today_window(reference: datetime | None = None) -> tuple[datetime, datetime]:
    ref = reference or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def window_for_store(store_id: str) -> tuple[datetime, datetime]:
    """Use the calendar day of the latest ingested event, else UTC today."""
    from app.database import last_event_timestamp

    last = last_event_timestamp(store_id)
    return today_window(last)
