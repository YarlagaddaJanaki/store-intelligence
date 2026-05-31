#!/usr/bin/env python3
"""
Process CCTV clips and emit structured store events.

Uses YOLOv8 + centroid tracking when ultralytics/opencv are available.
Falls back to replaying sample_events.jsonl for CI / missing footage.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.emit import EventEmitter, load_layout
from pipeline.tracker import CentroidTracker, new_visitor_id
from pipeline.zones import crossed_line, resolve_zone

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None
    np = None

try:
    from ultralytics import YOLO
except ImportError:  # pragma: no cover
    YOLO = None


PERSON_CLASS_ID = 0
DWELL_INTERVAL_MS = 30_000


def detect_staff_uniform(frame, box) -> bool:
    """Heuristic: saturated uniform tops (common retail staff vests)."""
    if cv2 is None or np is None:
        return False
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = frame[y1 : y1 + max(1, (y2 - y1) // 2), x1:x2]
    if crop.size == 0:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].mean()
    val = hsv[:, :, 2].mean()
    return sat > 90 and val > 80


def run_detector(
    video_path: Path,
    store_id: str,
    camera_id: str,
    layout: dict,
    output_path: Path,
    *,
    model_name: str = "yolov8n.pt",
    max_frames: int | None = None,
    stride: int = 2,
) -> int:
    if cv2 is None or YOLO is None:
        raise RuntimeError("opencv and ultralytics required for live detection")

    store_cfg = layout["stores"][store_id]
    camera_cfg = store_cfg["cameras"][camera_id]
    zones = camera_cfg.get("zones", [])
    entry_line = camera_cfg.get("entry_line")
    clip_start = datetime.fromisoformat(
        camera_cfg.get("clip_start", "2026-03-03T09:00:00Z").replace("Z", "+00:00")
    )

    model = YOLO(model_name)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(video_path)

    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dwell_frames = int((DWELL_INTERVAL_MS / 1000.0) * fps)

    tracker = CentroidTracker()
    count = 0
    frame_idx = 0
    prev_centroids: dict[int, tuple[float, float]] = {}
    seen_tracks: set[int] = set()
    is_entry_camera = camera_cfg.get("role") == "entry"

    if entry_line and max(entry_line["p1"] + entry_line["p2"]) <= 1.0:
        entry_line = {
            **entry_line,
            "p1": [entry_line["p1"][0] * frame_w, entry_line["p1"][1] * frame_h],
            "p2": [entry_line["p2"][0] * frame_w, entry_line["p2"][1] * frame_h],
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        emitter = EventEmitter(store_id, camera_id, clip_start, fps=fps, output=out)

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % stride != 0:
                frame_idx += 1
                continue
            if max_frames is not None and frame_idx > max_frames:
                break

            results = model(frame, verbose=False, classes=[PERSON_CLASS_ID])[0]
            detections: list[tuple[tuple[float, float, float, float], float, bool]] = []
            if results.boxes is not None:
                for box in results.boxes:
                    xyxy = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    is_staff = detect_staff_uniform(frame, xyxy)
                    detections.append((tuple(xyxy), conf, is_staff))

            states = tracker.update(detections, frame_idx)
            queue_depth = sum(
                1
                for s in states
                if s.active_zone == "BILLING" and not s.is_staff
            )

            for state in states:
                cx, cy = state.last_cx, state.last_cy
                prev = prev_centroids.get(state.track_id, (cx, cy))
                is_new_track = state.track_id not in seen_tracks
                if is_new_track:
                    seen_tracks.add(state.track_id)

                if is_entry_camera and is_new_track and not state.in_store:
                    emitter.emit(
                        visitor_id=state.visitor_id,
                        event_type="ENTRY",
                        frame_idx=frame_idx,
                        is_staff=state.is_staff,
                        confidence=0.8,
                    )
                    state.in_store = True
                    state.exited = False

                if entry_line:
                    direction = crossed_line(prev, (cx, cy), entry_line)
                    if direction == "inbound" and not state.in_store:
                        if state.exited:
                            emitter.emit(
                                visitor_id=state.visitor_id,
                                event_type="REENTRY",
                                frame_idx=frame_idx,
                                is_staff=state.is_staff,
                                confidence=0.75,
                            )
                        else:
                            emitter.emit(
                                visitor_id=state.visitor_id,
                                event_type="ENTRY",
                                frame_idx=frame_idx,
                                is_staff=state.is_staff,
                                confidence=0.85,
                            )
                        state.in_store = True
                        state.exited = False
                    elif direction == "outbound" and state.in_store:
                        emitter.emit(
                            visitor_id=state.visitor_id,
                            event_type="EXIT",
                            frame_idx=frame_idx,
                            is_staff=state.is_staff,
                            confidence=0.82,
                        )
                        state.in_store = False
                        state.exited = True

                zone_id = resolve_zone(cx, cy, zones, frame_w, frame_h)
                if zone_id != state.active_zone:
                    if state.active_zone:
                        emitter.emit(
                            visitor_id=state.visitor_id,
                            event_type="ZONE_EXIT",
                            frame_idx=frame_idx,
                            zone_id=state.active_zone,
                            is_staff=state.is_staff,
                            confidence=0.7,
                            metadata={"sku_zone": state.active_zone},
                        )
                    if zone_id:
                        emitter.emit(
                            visitor_id=state.visitor_id,
                            event_type="ZONE_ENTER",
                            frame_idx=frame_idx,
                            zone_id=zone_id,
                            is_staff=state.is_staff,
                            confidence=0.72,
                            metadata={"sku_zone": zone_id},
                        )
                        if zone_id == "BILLING" and queue_depth > 0 and not state.is_staff:
                            emitter.emit(
                                visitor_id=state.visitor_id,
                                event_type="BILLING_QUEUE_JOIN",
                                frame_idx=frame_idx,
                                zone_id=zone_id,
                                is_staff=False,
                                confidence=0.68,
                                metadata={
                                    "queue_depth": queue_depth,
                                    "sku_zone": zone_id,
                                },
                            )
                    state.active_zone = zone_id
                    state.zone_enter_frame = frame_idx if zone_id else None
                    state.last_dwell_emit_frame = frame_idx if zone_id else None

                if (
                    state.active_zone
                    and state.zone_enter_frame is not None
                    and state.last_dwell_emit_frame is not None
                    and frame_idx - state.last_dwell_emit_frame >= dwell_frames
                ):
                    dwell_ms = int((frame_idx - state.zone_enter_frame) / fps * 1000)
                    emitter.emit(
                        visitor_id=state.visitor_id,
                        event_type="ZONE_DWELL",
                        frame_idx=frame_idx,
                        zone_id=state.active_zone,
                        dwell_ms=dwell_ms,
                        is_staff=state.is_staff,
                        confidence=0.65,
                        metadata={"sku_zone": state.active_zone},
                    )
                    state.last_dwell_emit_frame = frame_idx

                prev_centroids[state.track_id] = (cx, cy)

            frame_idx += 1
            count += 1

    cap.release()
    return count


def replay_sample(sample_path: Path, output_path: Path, store_filter: str | None = None) -> int:
    count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sample_path.open(encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as out:
        for line in src:
            event = json.loads(line)
            if store_filter and event.get("store_id") != store_filter:
                continue
            out.write(json.dumps(event) + "\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Store Intelligence detection pipeline")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--clips-dir", default="data/clips")
    parser.add_argument("--layout", default="data/store_layout.json")
    parser.add_argument("--output", default="data/output/events.jsonl")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--replay-sample", action="store_true")
    parser.add_argument("--store-id", default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--stride", type=int, default=2)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_path = Path(args.output)
    sample = data_dir / "sample_events.jsonl"

    if args.replay_sample or not Path(args.clips_dir).exists():
        if not sample.exists():
            raise SystemExit("No clips or sample_events.jsonl found in data/")
        replay_sample(sample, output_path, args.store_id)
        print(f"Replayed sample events -> {output_path}")
        return

    layout = load_layout(Path(args.layout))
    total = 0
    clips_root = Path(args.clips_dir)
    for store_id, store_cfg in layout["stores"].items():
        if args.store_id and store_id != args.store_id:
            continue
        for camera_id in store_cfg["cameras"]:
            rel = store_cfg["cameras"][camera_id].get("clip_path")
            if not rel:
                continue
            video = clips_root / rel
            if not video.exists():
                continue
            out_file = output_path.parent / f"{store_id}_{camera_id}.jsonl"
            total += run_detector(
                video,
                store_id,
                camera_id,
                layout,
                out_file,
                model_name=args.model,
                max_frames=args.max_frames,
                stride=args.stride,
            )
            print(f"Processed {video} -> {out_file} ({total} frames)")

    if total > 0:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as merged:
            for sid, scfg in layout["stores"].items():
                if args.store_id and sid != args.store_id:
                    continue
                for cid in scfg["cameras"]:
                    part = output_path.parent / f"{sid}_{cid}.jsonl"
                    if part.exists():
                        merged.write(part.read_text(encoding="utf-8"))
        print(f"Merged all camera events -> {output_path}")

    if total == 0:
        replay_sample(sample, output_path, args.store_id)
        print(f"No clip files found; replayed sample -> {output_path}")


if __name__ == "__main__":
    main()
