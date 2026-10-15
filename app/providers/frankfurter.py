"""Frankfurter reference-FX adapter (no authentication required)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from .base import JsonHttpClient, ProviderError


@dataclass(frozen=True)
class FxRate:
    effective_date: date
    base_currency: str
    quote_currency: str
    rate: Decimal
    retrieved_at_utc: str
    source_url: str
    cache_status: str


class FrankfurterAdapter:
    BASE_URL = "https://api.frankfurter.dev/v2"

    def __init__(self, client: JsonHttpClient):
        self.client = client

    def fetch_rate(self, requested_date: date, base: str = "USD", quote: str = "INR") -> FxRate:
        base = base.upper()
        quote = quote.upper()
        url = f"{self.BASE_URL}/rate/{base}/{quote}?{urlencode({'date': requested_date.isoformat()})}"
        fetched = self.client.get_json(url, ttl_seconds=300)
        payload = fetched.payload
        if not isinstance(payload, dict):
            raise ProviderError("frankfurter", "invalid_schema", "Expected a rate object")
        try:
            effective = date.fromisoformat(str(payload["date"]))
            rate = Decimal(str(payload["rate"]))
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise ProviderError("frankfurter", "invalid_schema", "Invalid rate response") from exc
        if payload.get("base") != base or payload.get("quote") != quote or not rate.is_finite() or rate <= 0:
            raise ProviderError("frankfurter", "invalid_schema", "Unexpected currency pair or rate")
        # The historical API may return an effective source date. Never permit
        # an observation after the requested date.
        if effective > requested_date:
            raise ProviderError("frankfurter", "future_observation", "FX effective date is after requested date")
        return FxRate(effective, base, quote, rate, fetched.retrieved_at_utc, fetched.source_url, fetched.cache_status)


def align_fx_past_only(target_dates: list[date], rates: list[FxRate]) -> dict[date, FxRate | None]:
    """Align exact dates only; never look forward or silently forward-fill."""
    by_date = {item.effective_date: item for item in rates}
    return {day: by_date.get(day) for day in target_dates}


def usd_ounce_to_inr_gram(price_usd_per_troy_ounce: Decimal, usd_inr: Decimal) -> Decimal:
    if price_usd_per_troy_ounce <= 0 or usd_inr <= 0:
        raise ValueError("price and FX rate must be positive")
    return price_usd_per_troy_ounce * usd_inr / Decimal("31.1034768")
