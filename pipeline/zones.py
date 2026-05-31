"""Zone polygons and line-crossing helpers."""

from __future__ import annotations

from typing import Any


def point_in_polygon(px: float, py: float, polygon: list[list[float]]) -> bool:
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


def crossed_line(
    prev: tuple[float, float],
    curr: tuple[float, float],
    line: dict[str, Any],
) -> str | None:
    """
    Detect crossing of entry threshold line.
    Returns 'inbound', 'outbound', or None.
    """
    x1, y1 = line["p1"]
    x2, y2 = line["p2"]
    direction = line.get("inbound_side", "left")

    def side(px: float, py: float) -> float:
        return (y2 - y1) * (px - x1) - (x2 - x1) * (py - y1)

    prev_s = side(*prev)
    curr_s = side(*curr)
    if prev_s == 0 or curr_s == 0:
        return None
    if prev_s * curr_s >= 0:
        return None
    crossed_inbound = curr_s > prev_s if direction == "left" else curr_s < prev_s
    return "inbound" if crossed_inbound else "outbound"


def resolve_zone(
    cx: float,
    cy: float,
    zones: list[dict[str, Any]],
    frame_w: int,
    frame_h: int,
) -> str | None:
    for zone in zones:
        poly = zone.get("polygon_norm") or zone.get("polygon")
        if not poly:
            continue
        if _is_normalized(poly):
            scaled = [
                [p[0] * frame_w, p[1] * frame_h]
                for p in poly
            ]
        else:
            scaled = poly
        if point_in_polygon(cx, cy, scaled):
            return zone["zone_id"]
    return None


def _is_normalized(polygon: list[list[float]]) -> bool:
    return all(0 <= p[0] <= 1 and 0 <= p[1] <= 1 for p in polygon)
