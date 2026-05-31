import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO


@dataclass
class EventEmitter:
    store_id: str
    camera_id: str
    clip_start: datetime
    fps: float = 15.0
    session_seq: dict[str, int] = field(default_factory=dict)
    output: TextIO | None = None

    def _timestamp(self, frame_idx: int) -> str:
        offset = timedelta(seconds=frame_idx / self.fps)
        ts = self.clip_start.replace(tzinfo=timezone.utc) + offset
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _next_seq(self, visitor_id: str) -> int:
        self.session_seq[visitor_id] = self.session_seq.get(visitor_id, 0) + 1
        return self.session_seq[visitor_id]

    def emit(
        self,
        *,
        visitor_id: str,
        event_type: str,
        frame_idx: int,
        zone_id: str | None = None,
        dwell_ms: int = 0,
        is_staff: bool = False,
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = metadata or {}
        meta.setdefault("session_seq", self._next_seq(visitor_id))
        event = {
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": self.camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": self._timestamp(frame_idx),
            "zone_id": zone_id,
            "dwell_ms": int(dwell_ms),
            "is_staff": bool(is_staff),
            "confidence": float(round(confidence, 3)),
            "metadata": meta,
        }
        if self.output:
            self.output.write(json.dumps(event) + "\n")
        return event


def validate_event(event: dict[str, Any]) -> bool:
    required = {
        "event_id",
        "store_id",
        "camera_id",
        "visitor_id",
        "event_type",
        "timestamp",
        "dwell_ms",
        "is_staff",
        "confidence",
        "metadata",
    }
    return required.issubset(event.keys())


def load_layout(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)
