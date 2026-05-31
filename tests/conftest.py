import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    from app.config import settings as app_settings
    from app.database import set_db_available

    monkeypatch.setattr(app_settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(app_settings, "data_dir", tmp_path)
    set_db_available(True)
    if db_path.exists():
        db_path.unlink()
    init_db()
    yield TestClient(app)
    set_db_available(True)


@pytest.fixture()
def sample_events():
    path = Path("data/sample_events.jsonl")
    if not path.exists():
        from scripts.generate_sample_events import main as gen

        gen()
    events = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                events.append(json.loads(line))
    return events
