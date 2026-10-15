"""The refresh engine: pulls every needed dataset on its own cadence.

Design goals
------------
* Never call an upstream provider from inside an HTTP request handler.
* Refresh the fast-moving spot price every cycle (default 60s).
* Refresh slower sources (FX, daily bars, macro, news) on their own intervals,
  while still contributing to the same assembled snapshot.
* A failing provider degrades one section; it never takes the service down.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .config import Settings
from .providers import (
    FrankfurterAdapter,
    FredAdapter,
    GNewsAdapter,
    GoldPriceAdapter,
    JsonHttpClient,
    ProviderError,
    usd_ounce_to_inr_gram,
)
from .store import SnapshotStore

LOGGER = logging.getLogger("gold_api.refresh")


def _d(value: Decimal) -> str:
    return format(value, "f")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RefreshEngine:
    def __init__(self, settings: Settings, store: SnapshotStore):
        self.settings = settings
        self.store = store
        self.cache_dir = settings.cache_path
        self._last_run: dict[str, float] = {}
        self._last_bars: tuple[tuple[datetime, Decimal], ...] = ()

    # -- scheduling -------------------------------------------------------
    def _due(self, key: str, interval: int) -> bool:
        # A source that has never run is always due — including on the very first
        # cycle of a freshly booted container, where time.monotonic() is small.
        if interval <= 0 or key not in self._last_run:
            return True
        return (time.monotonic() - self._last_run[key]) >= interval

    def _mark(self, key: str) -> None:
        self._last_run[key] = time.monotonic()

    # -- individual sources ----------------------------------------------
    def refresh_gold(self) -> None:
        client = JsonHttpClient("goldprice.dev", self.cache_dir)
        adapter = GoldPriceAdapter(client, self.settings.goldprice_api_key or None)
        try:
            spot = adapter.fetch_spot()
        except ProviderError as exc:
            LOGGER.warning("gold auto-refresh failed: %s", exc)
            self.store.put_error("gold", exc.code, str(exc))
            self.store.put_provider("goldprice.dev", {"id": "goldprice.dev", "status": "error", "error_code": exc.code, "limitations": str(exc), "authentication": "optional API key"})
            return
        self.store.put_section(
            "gold",
            {
                "symbol": "XAU-USD-SPOT",
                "price_usd_per_troy_ounce": _d(spot.price_usd_per_troy_ounce),
                "price_usd_per_gram": _d(spot.price_usd_per_gram),
                "computed_at_utc": spot.computed_at_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "is_stale": spot.is_stale,
                "sources": list(spot.sources),
                "unit": "troy_ounce",
            },
            source_url=spot.source_url,
            fetched_at=spot.retrieved_at_utc,
        )
        self.store.put_provider(
            "goldprice.dev",
            {
                "id": "goldprice.dev",
                "status": "stale" if spot.is_stale else "available",
                "authentication": "optional API key; keyless is 15-minute delayed",
                "last_successful_update": spot.retrieved_at_utc,
                "latest_observation": spot.computed_at_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "coverage": "XAU/USD spot, keyless; deeper history with a key",
                "limitations": "International reference spot, not an exchange settlement or executable price; free commercial use requires visible attribution",
            },
        )

    def refresh_fx(self) -> None:
        client = JsonHttpClient("frankfurter", self.cache_dir)
        adapter = FrankfurterAdapter(client)
        today = _utc_now().date()
        try:
            fx = adapter.fetch_rate(today, "USD", "INR")
        except ProviderError as exc:
            LOGGER.warning("fx refresh failed: %s", exc)
            self.store.put_error("fx", exc.code, str(exc))
            self.store.put_provider("frankfurter", {"id": "frankfurter", "status": "error", "error_code": exc.code, "limitations": str(exc), "authentication": "none"})
            return
        self.store.put_section(
            "fx",
            {
                "base": fx.base_currency,
                "quote": fx.quote_currency,
                "rate": _d(fx.rate),
                "requested_date": today.isoformat(),
                "effective_date": fx.effective_date.isoformat(),
            },
            source_url=fx.source_url,
            fetched_at=fx.retrieved_at_utc,
        )
        self.store.put_provider(
            "frankfurter",
            {
                "id": "frankfurter",
                "status": "available",
                "authentication": "none",
                "last_successful_update": fx.retrieved_at_utc,
                "latest_observation": fx.effective_date.isoformat(),
                "coverage": "Daily reference FX; USD/INR",
                "limitations": "Reference mid-market/blended rate, not an executable quote",
            },
        )

    def refresh_bars(self) -> None:
        client = JsonHttpClient("goldprice.dev", self.cache_dir)
        adapter = GoldPriceAdapter(client, self.settings.goldprice_api_key or None)
        end = _utc_now().date()
        start = end - timedelta(days=max(1, self.settings.bars_history_days))
        try:
            bars = adapter.fetch_daily_bars(start, end)
        except ProviderError as exc:
            LOGGER.warning("bars refresh failed: %s", exc)
            self.store.put_error("bars", exc.code, str(exc))
            return
        self._last_bars = tuple((b.bar_start_utc, b.close_usd_per_troy_ounce) for b in bars)
        self.store.put_section(
            "bars",
            {
                "symbol": "XAU-USD-SPOT",
                "interval": "1d",
                "from": start.isoformat(),
                "to": end.isoformat(),
                "count": len(bars),
                "bars": [
                    {
                        "bar_start_utc": b.bar_start_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "open_usd_per_troy_ounce": _d(b.open_usd_per_troy_ounce),
                        "high_usd_per_troy_ounce": _d(b.high_usd_per_troy_ounce),
                        "low_usd_per_troy_ounce": _d(b.low_usd_per_troy_ounce),
                        "close_usd_per_troy_ounce": _d(b.close_usd_per_troy_ounce),
                        "is_closed": b.is_closed,
                    }
                    for b in bars
                ],
            },
        )

    def refresh_macro(self) -> None:
        series = self.settings.fred_series
        if not self.settings.fred_api_key:
            for series_id in series:
                self.store.put_provider(
                    f"fred:{series_id}",
                    {
                        "id": f"fred:{series_id}",
                        "status": "not_configured",
                        "authentication": "FRED_API_KEY required server-side",
                        "coverage": "Optional point-in-time macroeconomic observations",
                        "limitations": "Not used in signals; revision/vintage handling required",
                    },
                )
            self.store.put_section("macro", {"series": {}, "note": "FRED_API_KEY not configured"})
            return
        client = JsonHttpClient("fred", self.cache_dir)
        adapter = FredAdapter(client, self.settings.fred_api_key)
        today = _utc_now().date()
        start = today - timedelta(days=max(1, self.settings.macro_history_days))
        out: dict[str, Any] = {}
        for series_id in series:
            try:
                obs = adapter.fetch_series(series_id, start, today, as_of=today)
            except ProviderError as exc:
                LOGGER.warning("fred %s failed: %s", series_id, exc)
                self.store.put_provider(f"fred:{series_id}", {"id": f"fred:{series_id}", "status": "error", "error_code": exc.code, "limitations": str(exc), "authentication": "FRED_API_KEY required server-side"})
                continue
            out[series_id] = [
                {"date": o.observation_date.isoformat(), "value": _d(o.value) if o.value is not None else None}
                for o in obs
            ]
            self.store.put_provider(f"fred:{series_id}", {"id": f"fred:{series_id}", "status": "available", "authentication": "FRED_API_KEY required server-side", "coverage": f"FRED series {series_id}", "limitations": "Not used in signals"})
        self.store.put_section("macro", {"series": out, "as_of": today.isoformat()})

    def refresh_news(self) -> None:
        if not self.settings.gnews_api_key:
            self.store.put_provider(
                "gnews",
                {
                    "id": "gnews",
                    "status": "not_configured",
                    "authentication": "GNEWS_API_KEY required server-side",
                    "coverage": "Optional dated news context",
                    "limitations": "Context only; never enters quantitative signal formation",
                },
            )
            self.store.put_section("news", {"articles": [], "note": "GNEWS_API_KEY not configured"})
            return
        client = JsonHttpClient("gnews", self.cache_dir)
        adapter = GNewsAdapter(client, self.settings.gnews_api_key)
        end = _utc_now()
        start = end - timedelta(days=30)
        try:
            articles = adapter.search(self.settings.gnews_query, start, end, maximum=self.settings.gnews_max_articles)
        except ProviderError as exc:
            LOGGER.warning("gnews failed: %s", exc)
            self.store.put_error("news", exc.code, str(exc))
            self.store.put_provider("gnews", {"id": "gnews", "status": "error", "error_code": exc.code, "limitations": str(exc), "authentication": "GNEWS_API_KEY required server-side"})
            return
        self.store.put_section(
            "news",
            {
                "query": self.settings.gnews_query,
                "count": len(articles),
                "articles": [
                    {
                        "title": a.title,
                        "url": a.url,
                        "published_at_utc": a.published_at_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "source": a.source_name,
                        "description": a.description,
                    }
                    for a in articles
                ],
            },
        )
        self.store.put_provider("gnews", {"id": "gnews", "status": "available", "authentication": "GNEWS_API_KEY required server-side", "coverage": "Dated news context", "limitations": "Context only; never enters quantitative signal formation"})

    # -- orchestration ----------------------------------------------------
    def refresh_all(self, *, force: bool = False) -> None:
        """Run every source whose interval has elapsed (or all when forced)."""
        s = self.settings
        if force or self._due("gold", s.gold_interval_seconds):
            self.refresh_gold(); self._mark("gold")
        if force or self._due("fx", s.fx_interval_seconds):
            self.refresh_fx(); self._mark("fx")
        if force or self._due("bars", s.bars_interval_seconds):
            self.refresh_bars(); self._mark("bars")
        if force or self._due("macro", s.macro_interval_seconds):
            self.refresh_macro(); self._mark("macro")
        if force or self._due("news", s.news_interval_seconds):
            self.refresh_news(); self._mark("news")
        self.store.mark_cycle()
        self.store.save()

    # -- derived view -----------------------------------------------------
    def _derived(self) -> dict[str, Any]:
        gold = self.store.section("gold") or {}
        fx = self.store.section("fx") or {}
        gold_data = gold.get("data") or {}
        fx_data = fx.get("data") or {}
        out: dict[str, Any] = {}
        try:
            usd_oz = Decimal(str(gold_data.get("price_usd_per_troy_ounce")))
            usd_inr = Decimal(str(fx_data.get("rate")))
        except Exception:
            return out
        per_gram = usd_ounce_to_inr_gram(usd_oz, usd_inr)
        out["gold_reference_inr_per_gram"] = {
            "value": _d(per_gram),
            "gold_usd_per_troy_ounce": _d(usd_oz),
            "usd_inr": _d(usd_inr),
            "calculation": "XAU/USD per troy ounce / 31.1034768 * USD/INR",
            "gold_source": "goldprice.dev",
            "fx_source": "frankfurter",
            "classification": "contextual reference; not an exchange settlement or executable price",
        }
        return out

    def build_snapshot(self) -> dict[str, Any]:
        sections = {name: self.store.section(name) for name in SnapshotStore.SECTIONS}
        derived = self._derived()
        statuses = [s.get("status") for s in sections.values() if s]
        if not statuses or all(st == "error" for st in statuses):
            mode = "DEGRADED"
        elif any(st == "error" for st in statuses):
            mode = "PARTIAL"
        else:
            mode = "LIVE"
        snapshot = {
            "schema_version": self.settings.schema_version,
            "engine_version": self.settings.engine_version,
            "service": self.settings.service_name,
            "generated_at_utc": _utc_now().isoformat().replace("+00:00", "Z"),
            "mode": mode,
            "refresh_interval_seconds": self.settings.refresh_interval_seconds,
            "sections": sections,
            "derived": derived,
            "providers": self.store.providers(),
            "meta": self.store.meta(),
        }
        return snapshot
