"""Data-provider adapters for the Gold API.

Each adapter is a thin, schema-validating wrapper over one upstream source.
All of them raise ``ProviderError`` on failure so the refresh engine can record
per-provider health without crashing the service.
"""

from .base import FetchResult, JsonHttpClient, ProviderError, TransportResponse
from .frankfurter import FrankfurterAdapter, FxRate, usd_ounce_to_inr_gram
from .fred import FredAdapter, FredObservation
from .gnews import GNewsAdapter, NewsArticle
from .goldprice import GoldBar, GoldPriceAdapter, GoldSpot

__all__ = [
    "FetchResult",
    "JsonHttpClient",
    "ProviderError",
    "TransportResponse",
    "FrankfurterAdapter",
    "FxRate",
    "usd_ounce_to_inr_gram",
    "FredAdapter",
    "FredObservation",
    "GNewsAdapter",
    "NewsArticle",
    "GoldBar",
    "GoldPriceAdapter",
    "GoldSpot",
]
