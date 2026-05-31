# PROMPT: Write unit tests for pipeline emit.py, tracker re-id, zone polygon helpers,
# and sample replay mode without requiring GPU or video files.
# CHANGES MADE: Added tracker re-entry visitor_id reuse test, emit schema field test,
# and replay_sample integration using generated sample_events.jsonl.

import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from pipeline.emit import EventEmitter, validate_event
from pipeline.tracker import CentroidTracker
from pipeline.zones import point_in_polygon, resolve_zone


def test_emit_event_schema():
    buf = StringIO()
    emitter = EventEmitter(
        "STORE_BLR_002",
        "CAM_ENTRY_01",
        datetime(2026, 3, 3, 9, 0, tzinfo=timezone.utc),
        output=buf,
    )
    event = emitter.emit(
        visitor_id="VIS_test01",
        event_type="ENTRY",
        frame_idx=30,
        confidence=0.42,
    )
    assert validate_event(event)
    parsed = json.loads(buf.getvalue().strip())
    assert parsed["event_type"] == "ENTRY"
    assert parsed["confidence"] == 0.42


def test_tracker_reid_after_exit():
    tracker = CentroidTracker()
    box = (100.0, 200.0, 140.0, 320.0)
    tracker.update([(box, 0.9, False)], frame_idx=10)
    vid = list(tracker.tracks.values())[0].visitor_id
    for _ in range(35):
        tracker.update([], frame_idx=11 + _)
    tracker._recent_exits.append((120.0, 260.0, vid, 50))
    tracker.update([((118.0, 255.0, 150.0, 330.0), 0.88, False)], frame_idx=60)
    new_vid = list(tracker.tracks.values())[0].visitor_id
    assert new_vid == vid


def test_zone_polygon():
    square = [[0, 0], [1, 0], [1, 1], [0, 1]]
    assert point_in_polygon(0.5, 0.5, square)
    assert not point_in_polygon(1.5, 0.5, square)


def test_resolve_zone_normalized():
    zones = [{"zone_id": "SKINCARE", "polygon_norm": [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]}]
    assert resolve_zone(50, 50, zones, 200, 200) == "SKINCARE"


def test_replay_sample(tmp_path):
    sample = Path("data/sample_events.jsonl")
    if not sample.exists():
        from scripts.generate_sample_events import main as gen

        gen()
    out = tmp_path / "out.jsonl"
    from pipeline.detect import replay_sample

    count = replay_sample(sample, out)
    assert count > 0
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == count
