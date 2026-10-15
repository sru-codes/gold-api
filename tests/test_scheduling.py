"""Scheduling rules, including the fresh-host first-cycle regression."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.refresh import RefreshEngine
from app.store import SnapshotStore


def _engine(tmp_path: Path) -> RefreshEngine:
    settings = replace(Settings.from_env(), data_dir=str(tmp_path), cache_dir=str(tmp_path / "cache"))
    return RefreshEngine(settings, SnapshotStore(state_path=tmp_path / "published" / "snap.json"))


def test_never_run_source_is_due_on_a_fresh_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: on a freshly booted host time.monotonic() can be smaller than a
    # source's interval, which previously made slow sources "not due" forever on
    # the first cycle. A source that has never run must always be due.
    monkeypatch.setattr("app.refresh.time.monotonic", lambda: 5.0)
    engine = _engine(tmp_path)
    assert engine._due("bars", 3600) is True
    assert engine._due("macro", 3600) is True
    assert engine._due("news", 900) is True


def test_not_due_after_running(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine._mark("fx")
    assert engine._due("fx", 300) is False


def test_non_positive_interval_is_always_due(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine._mark("gold")
    assert engine._due("gold", 0) is True


def test_refresh_all_first_cycle_runs_every_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path)
    calls: list[str] = []
    for name in ("refresh_gold", "refresh_fx", "refresh_bars", "refresh_macro", "refresh_news"):
        monkeypatch.setattr(engine, name, (lambda n: (lambda *a, **k: calls.append(n)))(name))
    engine.refresh_all()
    assert calls == ["refresh_gold", "refresh_fx", "refresh_bars", "refresh_macro", "refresh_news"]
    assert engine.store.meta()["cycle_count"] == 1


def test_refresh_all_skips_sources_not_yet_due(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path)
    calls: list[str] = []
    for name in ("refresh_gold", "refresh_fx", "refresh_bars", "refresh_macro", "refresh_news"):
        monkeypatch.setattr(engine, name, (lambda n: (lambda *a, **k: calls.append(n)))(name))
    # Simulate everything having just run.
    for key in ("gold", "fx", "bars", "macro", "news"):
        engine._mark(key)
    engine.refresh_all()
    assert calls == []
    # Forcing still runs everything.
    engine.refresh_all(force=True)
    assert calls == ["refresh_gold", "refresh_fx", "refresh_bars", "refresh_macro", "refresh_news"]


def test_build_snapshot_shape(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine.store.put_section("gold", {"price_usd_per_troy_ounce": "2000", "price_usd_per_gram": "64.3"})
    engine.store.put_section("fx", {"rate": "85"})
    snapshot: dict[str, Any] = engine.build_snapshot()
    assert snapshot["mode"] in {"LIVE", "PARTIAL", "DEGRADED"}
    assert set(snapshot["sections"]) == {"gold", "fx", "bars", "macro", "news"}
    derived = snapshot["derived"]["gold_reference_inr_per_gram"]
    assert derived["value"].startswith("5465.6")
    assert derived["gold_source"] == "goldprice.dev"
    assert derived["fx_source"] == "frankfurter"
