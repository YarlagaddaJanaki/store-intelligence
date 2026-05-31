from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

EventType = Literal[
    "ENTRY",
    "EXIT",
    "ZONE_ENTER",
    "ZONE_EXIT",
    "ZONE_DWELL",
    "BILLING_QUEUE_JOIN",
    "BILLING_QUEUE_ABANDON",
    "REENTRY",
]

Severity = Literal["INFO", "WARN", "CRITICAL"]


class EventMetadata(BaseModel):
    queue_depth: int | None = None
    sku_zone: str | None = None
    session_seq: int | None = None


class StoreEvent(BaseModel):
    event_id: UUID
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: EventType
    timestamp: datetime
    zone_id: str | None = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ValueError("timestamp must be ISO-8601")


class IngestRequest(BaseModel):
    events: list[Any] = Field(max_length=500)


class IngestErrorItem(BaseModel):
    index: int
    event_id: str | None = None
    detail: str


class IngestResponse(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    errors: list[IngestErrorItem]


class ZoneMetric(BaseModel):
    zone_id: str
    avg_dwell_ms: float
    visit_count: int


class StoreMetricsResponse(BaseModel):
    store_id: str
    date: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_per_zone: list[ZoneMetric]
    queue_depth: int
    abandonment_rate: float


class FunnelStage(BaseModel):
    stage: str
    count: int
    drop_off_pct: float | None = None


class FunnelResponse(BaseModel):
    store_id: str
    date: str
    stages: list[FunnelStage]


class HeatmapZone(BaseModel):
    zone_id: str
    visit_frequency: float
    avg_dwell_ms: float


class HeatmapResponse(BaseModel):
    store_id: str
    date: str
    zones: list[HeatmapZone]
    data_confidence: bool


class AnomalyItem(BaseModel):
    type: str
    severity: Severity
    message: str
    suggested_action: str
    detected_at: datetime


class AnomaliesResponse(BaseModel):
    store_id: str
    anomalies: list[AnomalyItem]


class StoreHealthItem(BaseModel):
    store_id: str
    last_event_at: datetime | None
    stale: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    stores: list[StoreHealthItem]
    warnings: list[str]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    trace_id: str | None = None
