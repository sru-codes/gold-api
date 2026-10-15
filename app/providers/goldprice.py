"""goldprice.dev XAU/USD adapter (keyless-friendly)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

from .base import JsonHttpClient, ProviderError

TROY_OUNCE_GRAMS = Decimal("31.1034768")


@dataclass(frozen=True)
class GoldSpot:
    price_usd_per_troy_ounce: Decimal
    price_usd_per_gram: Decimal
    computed_at_utc: datetime
    is_stale: bool
    retrieved_at_utc: str
    source_url: str
    cache_status: str
    sources: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class GoldBar:
    bar_start_utc: datetime
    open_usd_per_troy_ounce: Decimal
    high_usd_per_troy_ounce: Decimal
    low_usd_per_troy_ounce: Decimal
    close_usd_per_troy_ounce: Decimal
    is_closed: bool


class GoldPriceAdapter:
    BASE_URL = "https://api.goldprice.dev/v1"

    def __init__(self, client: JsonHttpClient, api_key: str | None = None):
        self.client = client
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _auth_scope(self) -> str:
        return "authenticated" if self.api_key else "anonymous"

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError) as exc:
            raise ProviderError("goldprice.dev", "invalid_schema", f"Invalid {field}") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ProviderError("goldprice.dev", "invalid_schema", f"Invalid {field}")
        return parsed

    def fetch_spot(self) -> GoldSpot:
        url = f"{self.BASE_URL}/prices?{urlencode({'symbol': 'XAU-USD-SPOT', 'include': 'sources'})}"
        fetched = self.client.get_json(
            url, headers=self._headers(), ttl_seconds=60, auth_scope=self._auth_scope()
        )
        rows = fetched.payload.get("symbols") if isinstance(fetched.payload, dict) else None
        if not isinstance(rows, list) or len(rows) != 1:
            raise ProviderError("goldprice.dev", "invalid_schema", "Expected exactly one XAU spot row")
        row = rows[0]
        if not isinstance(row, dict) or row.get("symbol") != "XAU" or row.get("quote_currency") != "USD" or row.get("unit") != "troy_ounce" or row.get("contract_type") != "spot":
            raise ProviderError("goldprice.dev", "invalid_schema", "Unexpected XAU spot identity or units")
        price = self._decimal(row.get("price"), "price")
        try:
            computed = datetime.fromisoformat(str(row["computed_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError) as exc:
            raise ProviderError("goldprice.dev", "invalid_schema", "Invalid computed_at") from exc
        return GoldSpot(
            price,
            price / TROY_OUNCE_GRAMS,
            computed,
            bool(row.get("is_stale", False)),
            fetched.retrieved_at_utc,
            fetched.source_url,
            fetched.cache_status,
            tuple(row.get("sources") or ()),
        )

    def fetch_daily_bars(self, start: date, end: date) -> tuple[GoldBar, ...]:
        if end < start:
            raise ValueError("end date precedes start date")
        url = f"{self.BASE_URL}/bars?{urlencode({'symbol': 'XAU-USD-SPOT', 'interval': '1d', 'from': start.isoformat(), 'to': end.isoformat(), 'limit': '10000'})}"
        fetched = self.client.get_json(
            url, headers=self._headers(), ttl_seconds=3600, auth_scope=self._auth_scope()
        )
        payload = fetched.payload
        if not isinstance(payload, dict) or payload.get("symbol") != "XAU-USD-SPOT" or payload.get("interval") != "1d" or not isinstance(payload.get("bars"), list):
            raise ProviderError("goldprice.dev", "invalid_schema", "Unexpected bars response")
        if payload.get("next_cursor"):
            raise ProviderError("goldprice.dev", "pagination_required", "History response was paginated; narrow the range or add pagination")
        bars: list[GoldBar] = []
        for row in payload["bars"]:
            if not isinstance(row, dict) or not row.get("is_closed"):
                continue
            try:
                timestamp = datetime.fromisoformat(str(row["bar_start"]).replace("Z", "+00:00"))
            except (KeyError, ValueError) as exc:
                raise ProviderError("goldprice.dev", "invalid_schema", "Invalid bar timestamp") from exc
            bars.append(GoldBar(
                timestamp,
                self._decimal(row.get("open"), "open"),
                self._decimal(row.get("high"), "high"),
                self._decimal(row.get("low"), "low"),
                self._decimal(row.get("close"), "close"),
                True,
            ))
        bars.sort(key=lambda item: item.bar_start_utc)
        return tuple(bars)
