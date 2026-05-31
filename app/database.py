import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import settings

_db_available = True


def set_db_available(available: bool) -> None:
    global _db_available
    _db_available = available


def is_db_available() -> bool:
    return _db_available


def _ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    path = settings.sqlite_path
    _ensure_parent(path)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                visitor_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                zone_id TEXT,
                dwell_ms INTEGER NOT NULL,
                is_staff INTEGER NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_store_ts
                ON events(store_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_visitor
                ON events(visitor_id, timestamp);
            CREATE TABLE IF NOT EXISTS daily_baselines (
                store_id TEXT NOT NULL,
                metric_date TEXT NOT NULL,
                conversion_rate REAL NOT NULL,
                PRIMARY KEY (store_id, metric_date)
            );
            """
        )


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    if not is_db_available():
        raise sqlite3.OperationalError("database unavailable")
    conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_event(event: dict[str, Any]) -> bool:
    """Insert event; returns False if duplicate event_id."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM events WHERE event_id = ?",
            (str(event["event_id"]),),
        ).fetchone()
        if existing:
            return False
        conn.execute(
            """
            INSERT INTO events (
                event_id, store_id, camera_id, visitor_id, event_type,
                timestamp, zone_id, dwell_ms, is_staff, confidence, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event["event_id"]),
                event["store_id"],
                event["camera_id"],
                event["visitor_id"],
                event["event_type"],
                event["timestamp"].isoformat()
                if isinstance(event["timestamp"], datetime)
                else event["timestamp"],
                event.get("zone_id"),
                event.get("dwell_ms", 0),
                1 if event.get("is_staff") else 0,
                event["confidence"],
                json.dumps(event.get("metadata") or {}),
            ),
        )
        return True


def fetch_events(
    store_id: str,
    start: datetime,
    end: datetime,
    *,
    customer_only: bool = True,
) -> list[dict[str, Any]]:
    query = """
        SELECT * FROM events
        WHERE store_id = ? AND timestamp >= ? AND timestamp < ?
    """
    params: list[Any] = [store_id, start.isoformat(), end.isoformat()]
    if customer_only:
        query += " AND is_staff = 0"
    query += " ORDER BY timestamp ASC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_event(row) for row in rows]


def last_event_timestamp(store_id: str) -> datetime | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT MAX(timestamp) AS ts FROM events WHERE store_id = ?
            """,
            (store_id,),
        ).fetchone()
    if not row or not row["ts"]:
        return None
    return datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))


def list_store_ids() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT store_id FROM events ORDER BY store_id"
        ).fetchall()
    return [row["store_id"] for row in rows]


def upsert_baseline(store_id: str, metric_date: str, conversion_rate: float) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_baselines (store_id, metric_date, conversion_rate)
            VALUES (?, ?, ?)
            ON CONFLICT(store_id, metric_date) DO UPDATE SET
                conversion_rate = excluded.conversion_rate
            """,
            (store_id, metric_date, conversion_rate),
        )


def avg_conversion_last_n_days(store_id: str, end_date: str, days: int = 7) -> float | None:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT conversion_rate
            FROM daily_baselines
            WHERE store_id = ? AND metric_date < ?
            ORDER BY metric_date DESC
            LIMIT ?
            """,
            (store_id, end_date, days),
        ).fetchall()
    if not rows:
        return None
    return sum(float(r["conversion_rate"]) for r in rows) / len(rows)


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    meta = json.loads(row["metadata_json"] or "{}")
    ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return {
        "event_id": row["event_id"],
        "store_id": row["store_id"],
        "camera_id": row["camera_id"],
        "visitor_id": row["visitor_id"],
        "event_type": row["event_type"],
        "timestamp": ts,
        "zone_id": row["zone_id"],
        "dwell_ms": row["dwell_ms"],
        "is_staff": bool(row["is_staff"]),
        "confidence": row["confidence"],
        "metadata": meta,
    }
