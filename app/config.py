"""Environment-driven configuration for the Gold API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Everything is overridable via environment variables."""

    # Master loop cadence. The whole snapshot is re-assembled at least this often.
    refresh_interval_seconds: int = 60

    # Per-provider cadences (seconds). Cheap/live sources refresh every minute.
    gold_interval_seconds: int = 60
    fx_interval_seconds: int = 300
    bars_interval_seconds: int = 3600
    macro_interval_seconds: int = 3600
    news_interval_seconds: int = 900

    # How much history to keep in the bars section.
    bars_history_days: int = 30
    macro_history_days: int = 90

    # Optional credentials. The service runs fully without any of them.
    goldprice_api_key: str = ""
    fred_api_key: str = ""
    gnews_api_key: str = ""

    # Optional context selectors.
    fred_series: list[str] = field(default_factory=lambda: ["DGS10"])
    gnews_query: str = "gold price"
    gnews_max_articles: int = 10

    # Persistence for the provider response cache and the published snapshot.
    data_dir: str = "/data"
    cache_dir: str = "/data/cache"

    # Optional bearer token protecting POST /api/v1/refresh. Empty = refresh is open.
    admin_token: str = ""

    # CORS: comma-separated origins, or "*" for any.
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    # Presentation metadata.
    service_name: str = "gold-api"
    engine_version: str = "1.0.0"
    schema_version: str = "1"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def cache_path(self) -> Path:
        return Path(self.cache_dir)

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = os.getenv("DATA_DIR", "/data")
        return cls(
            refresh_interval_seconds=_env_int("REFRESH_INTERVAL_SECONDS", 60),
            gold_interval_seconds=_env_int("GOLD_INTERVAL_SECONDS", 60),
            fx_interval_seconds=_env_int("FX_INTERVAL_SECONDS", 300),
            bars_interval_seconds=_env_int("BARS_INTERVAL_SECONDS", 3600),
            macro_interval_seconds=_env_int("MACRO_INTERVAL_SECONDS", 3600),
            news_interval_seconds=_env_int("NEWS_INTERVAL_SECONDS", 900),
            bars_history_days=_env_int("BARS_HISTORY_DAYS", 30),
            macro_history_days=_env_int("MACRO_HISTORY_DAYS", 90),
            goldprice_api_key=os.getenv("GOLDPRICE_API_KEY", ""),
            fred_api_key=os.getenv("FRED_API_KEY", ""),
            gnews_api_key=os.getenv("GNEWS_API_KEY", ""),
            fred_series=_env_list("FRED_SERIES", ["DGS10"]),
            gnews_query=os.getenv("GNEWS_QUERY", "gold price"),
            gnews_max_articles=_env_int("GNEWS_MAX_ARTICLES", 10),
            data_dir=data_dir,
            cache_dir=os.getenv("CACHE_DIR", f"{data_dir}/cache"),
            admin_token=os.getenv("ADMIN_TOKEN", ""),
            cors_origins=_env_list("CORS_ORIGINS", ["*"]),
            service_name=os.getenv("SERVICE_NAME", "gold-api"),
            engine_version=os.getenv("ENGINE_VERSION", "1.0.0"),
        )
