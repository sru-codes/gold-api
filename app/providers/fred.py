"""Optional point-in-time FRED adapter; credentials stay server-side."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from .base import JsonHttpClient, ProviderError


@dataclass(frozen=True)
class FredObservation:
    observation_date: date
    value: Decimal | None
    realtime_start: date
    realtime_end: date


class FredAdapter:
    BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self, client: JsonHttpClient, api_key: str | None):
        self.client = client
        self.api_key = api_key

    def fetch_series(self, series_id: str, start: date, end: date, *, as_of: date) -> tuple[FredObservation, ...]:
        if not self.api_key:
            raise ProviderError("fred", "missing_credentials", "FRED_API_KEY is required")
        if end > as_of:
            raise ValueError("observation end cannot be after the point-in-time as_of date")
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
            "realtime_start": as_of.isoformat(),
            "realtime_end": as_of.isoformat(),
        }
        # The key is in the query because FRED requires it; the cache namespace
        # prevents cross-account reuse. Provider docs define this endpoint.
        url = f"{self.BASE_URL}/series/observations?{urlencode(params)}"
        fetched = self.client.get_json(
            url,
            ttl_seconds=3600,
            auth_scope="authenticated",
            display_url=f"{self.BASE_URL}/series/observations?series_id={series_id}&api_key=REDACTED",
        )
        rows = fetched.payload.get("observations") if isinstance(fetched.payload, dict) else None
        if not isinstance(rows, list):
            raise ProviderError("fred", "invalid_schema", "Expected observations array")
        observations = []
        for row in rows:
            try:
                value = None if row["value"] == "." else Decimal(str(row["value"]))
                item = FredObservation(
                    date.fromisoformat(row["date"]), value,
                    date.fromisoformat(row["realtime_start"]),
                    date.fromisoformat(row["realtime_end"]),
                )
            except (KeyError, ValueError, InvalidOperation) as exc:
                raise ProviderError("fred", "invalid_schema", "Invalid FRED observation") from exc
            if item.observation_date > as_of or item.realtime_start > as_of:
                raise ProviderError("fred", "future_observation", "FRED response contains future-known data")
            observations.append(item)
        return tuple(observations)
