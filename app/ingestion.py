from typing import Any

from pydantic import ValidationError

from app.database import insert_event
from app.models import IngestErrorItem, IngestResponse, StoreEvent


def ingest_events(raw_events: list[dict[str, Any]]) -> IngestResponse:
    accepted = 0
    duplicates = 0
    rejected = 0
    errors: list[IngestErrorItem] = []

    for index, raw in enumerate(raw_events):
        try:
            event = StoreEvent.model_validate(raw)
            payload = event.model_dump(mode="json")
            payload["timestamp"] = event.timestamp
            inserted = insert_event(payload)
            if inserted:
                accepted += 1
            else:
                duplicates += 1
        except ValidationError as exc:
            rejected += 1
            event_id = raw.get("event_id") if isinstance(raw, dict) else None
            errors.append(
                IngestErrorItem(
                    index=index,
                    event_id=str(event_id) if event_id else None,
                    detail=str(exc.errors()[0]["msg"]) if exc.errors() else str(exc),
                )
            )
        except Exception as exc:
            rejected += 1
            event_id = raw.get("event_id") if isinstance(raw, dict) else None
            errors.append(
                IngestErrorItem(
                    index=index,
                    event_id=str(event_id) if event_id else None,
                    detail=str(exc),
                )
            )

    return IngestResponse(
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
        errors=errors,
    )
