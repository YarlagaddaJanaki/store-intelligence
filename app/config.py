from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STORE_INTEL_")

    database_url: str = "sqlite:///./data/store_intel.db"
    data_dir: Path = Path("data")
    pos_csv: Path = Path("data/pos_transactions.csv")
    store_layout: Path = Path("data/store_layout.json")
    stale_feed_minutes: int = 10
    conversion_window_minutes: int = 5
    dwell_emit_interval_ms: int = 30_000
    min_sessions_for_confidence: int = 20

    @property
    def sqlite_path(self) -> str:
        if self.database_url.startswith("sqlite:///"):
            return self.database_url.replace("sqlite:///", "", 1)
        return "./data/store_intel.db"


settings = Settings()
