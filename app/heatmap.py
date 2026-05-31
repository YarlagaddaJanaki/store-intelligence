from datetime import datetime

from app.config import settings
from app.database import fetch_events
from app.models import HeatmapResponse, HeatmapZone
from app.sessions import build_sessions, today_window, window_for_store


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    max_v = max(values) or 1.0
    return [round(100.0 * v / max_v, 2) for v in values]


def compute_heatmap(store_id: str, day: datetime | None = None) -> HeatmapResponse:
    start, end = today_window(day) if day else window_for_store(store_id)
    events = fetch_events(store_id, start, end, customer_only=True)
    sessions = build_sessions(events)

    visit_counts: dict[str, int] = {}
    dwell_sums: dict[str, list[int]] = {}

    for session in sessions.values():
        for zone in session["zones_visited"]:
            visit_counts[zone] = visit_counts.get(zone, 0) + 1
        for zone, dwells in session["dwell_by_zone"].items():
            dwell_sums.setdefault(zone, []).extend(dwells)

    zones = sorted(set(visit_counts) | set(dwell_sums))
    raw_freq = [float(visit_counts.get(z, 0)) for z in zones]
    norm_freq = _normalize(raw_freq)

    heatmap_zones = [
        HeatmapZone(
            zone_id=zone,
            visit_frequency=norm_freq[idx],
            avg_dwell_ms=(
                sum(dwell_sums.get(zone, [])) / len(dwell_sums[zone])
                if dwell_sums.get(zone)
                else 0.0
            ),
        )
        for idx, zone in enumerate(zones)
    ]

    return HeatmapResponse(
        store_id=store_id,
        date=start.date().isoformat(),
        zones=heatmap_zones,
        data_confidence=len(sessions) >= settings.min_sessions_for_confidence,
    )
