"""Multi-object tracking and visit session identity."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field


def new_visitor_id() -> str:
    return f"VIS_{secrets.token_hex(3)}"


@dataclass
class TrackState:
    track_id: int
    visitor_id: str
    is_staff: bool = False
    last_cx: float = 0.0
    last_cy: float = 0.0
    active_zone: str | None = None
    zone_enter_frame: int | None = None
    last_dwell_emit_frame: int | None = None
    in_store: bool = False
    exited: bool = False
    reid_memory: dict[str, float] = field(default_factory=dict)


class CentroidTracker:
    """Lightweight IoU + centroid tracker suitable for 15fps retail CCTV."""

    def __init__(self, max_miss: int = 30, iou_threshold: float = 0.25) -> None:
        self.max_miss = max_miss
        self.iou_threshold = iou_threshold
        self.tracks: dict[int, TrackState] = {}
        self._next_id = 1
        self._recent_exits: list[tuple[float, float, str, int]] = []

    @staticmethod
    def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        inter = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
        if inter <= 0:
            return 0.0
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        return inter / (area_a + area_b - inter + 1e-6)

    def _match(self, box: tuple[float, float, float, float]) -> int | None:
        best_id = None
        best_iou = self.iou_threshold
        for track_id, state in self.tracks.items():
            pseudo = (
                state.last_cx - 20,
                state.last_cy - 40,
                state.last_cx + 20,
                state.last_cy + 40,
            )
            score = self._iou(box, pseudo)
            if score > best_iou:
                best_iou = score
                best_id = track_id
        return best_id

    def _try_reid(self, cx: float, cy: float, frame_idx: int, window: int = 450) -> str | None:
        for ex, ey, visitor_id, exit_frame in self._recent_exits:
            if frame_idx - exit_frame > window:
                continue
            dist = ((cx - ex) ** 2 + (cy - ey) ** 2) ** 0.5
            if dist < 80:
                return visitor_id
        return None

    def update(
        self,
        detections: list[tuple[tuple[float, float, float, float], float, bool]],
        frame_idx: int,
    ) -> list[TrackState]:
        assigned: set[int] = set()
        for box, confidence, is_staff in detections:
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            track_id = self._match(box)
            if track_id is None:
                reid_vid = self._try_reid(cx, cy, frame_idx)
                track_id = self._next_id
                self._next_id += 1
                visitor_id = reid_vid or new_visitor_id()
                self.tracks[track_id] = TrackState(
                    track_id=track_id,
                    visitor_id=visitor_id,
                    is_staff=is_staff,
                )
            state = self.tracks[track_id]
            state.last_cx, state.last_cy = cx, cy
            state.is_staff = is_staff
            assigned.add(track_id)

        to_delete = []
        for track_id, state in self.tracks.items():
            if track_id not in assigned:
                state.reid_memory["miss"] = state.reid_memory.get("miss", 0) + 1
                if state.reid_memory["miss"] > self.max_miss:
                    if state.in_store and not state.exited:
                        self._recent_exits.append(
                            (state.last_cx, state.last_cy, state.visitor_id, frame_idx)
                        )
                    to_delete.append(track_id)
        for track_id in to_delete:
            del self.tracks[track_id]
        return list(self.tracks.values())
