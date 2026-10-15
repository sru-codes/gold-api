"""Provider schema validation, driven by an injected fake transport (no network)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.providers.base import JsonHttpClient, ProviderError, TransportResponse
from app.providers.frankfurter import FrankfurterAdapter
from app.providers.fred import FredAdapter
from app.providers.gnews import GNewsAdapter
from app.providers.goldprice import GoldPriceAdapter


def _client(tmp_path: Path, payload: Any, status: int = 200) -> JsonHttpClient:
    body = json.dumps(payload).encode()

    def transport(url: str, headers: Any, timeout: float) -> TransportResponse:
        return TransportResponse(status, {}, body)

    return JsonHttpClient("test", tmp_path, transport=transport, sleeper=lambda _: None)


# --- goldprice.dev ----------------------------------------------------------

VALID_SPOT = {
    "symbols": [
        {
            "symbol": "XAU",
            "quote_currency": "USD",
            "unit": "troy_ounce",
            "contract_type": "spot",
            "price": "2000",
            "computed_at": "2026-01-01T00:00:00Z",
            "is_stale": False,
            "sources": [{"source": "oracle.xau_usd", "price": "2000"}],
        }
    ]
}


def test_gold_spot_parses_valid_payload(tmp_path: Path) -> None:
    adapter = GoldPriceAdapter(_client(tmp_path, VALID_SPOT))
    spot = adapter.fetch_spot()
    assert spot.price_usd_per_troy_ounce == Decimal("2000")
    assert spot.price_usd_per_gram == Decimal("2000") / Decimal("31.1034768")
    assert spot.is_stale is False


def test_gold_spot_rejects_wrong_symbol(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(VALID_SPOT))
    bad["symbols"][0]["symbol"] = "XAG"
    with pytest.raises(ProviderError) as excinfo:
        GoldPriceAdapter(_client(tmp_path, bad)).fetch_spot()
    assert excinfo.value.code == "invalid_schema"


def test_gold_spot_rejects_non_positive_price(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(VALID_SPOT))
    bad["symbols"][0]["price"] = "0"
    with pytest.raises(ProviderError):
        GoldPriceAdapter(_client(tmp_path, bad)).fetch_spot()


# --- frankfurter ------------------------------------------------------------

def test_frankfurter_parses_valid_payload(tmp_path: Path) -> None:
    payload = {"date": "2026-01-01", "base": "USD", "quote": "INR", "rate": "85.25"}
    rate = FrankfurterAdapter(_client(tmp_path, payload)).fetch_rate(date(2026, 1, 1))
    assert rate.rate == Decimal("85.25")
    assert rate.effective_date == date(2026, 1, 1)


def test_frankfurter_rejects_future_effective_date(tmp_path: Path) -> None:
    payload = {"date": "2026-02-01", "base": "USD", "quote": "INR", "rate": "85.25"}
    with pytest.raises(ProviderError) as excinfo:
        FrankfurterAdapter(_client(tmp_path, payload)).fetch_rate(date(2026, 1, 1))
    assert excinfo.value.code == "future_observation"


# --- fred / gnews (credential-gated) ---------------------------------------

def test_fred_requires_credentials(tmp_path: Path) -> None:
    adapter = FredAdapter(_client(tmp_path, {"observations": []}), None)
    with pytest.raises(ProviderError) as excinfo:
        adapter.fetch_series("DGS10", date(2026, 1, 1), date(2026, 1, 31), as_of=date(2026, 1, 31))
    assert excinfo.value.code == "missing_credentials"


def test_gnews_requires_credentials(tmp_path: Path) -> None:
    adapter = GNewsAdapter(_client(tmp_path, {"articles": []}), None)
    now = date(2026, 1, 10)
    with pytest.raises(ProviderError) as excinfo:
        adapter.search("gold", now, now + timedelta(days=1))
    assert excinfo.value.code == "missing_credentials"
