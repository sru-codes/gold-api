"""Snapshot store behaviour: isolation, error retention, persistence."""

from __future__ import annotations

from pathlib import Path

from app.store import SnapshotStore


def test_put_and_read_section() -> None:
    store = SnapshotStore()
    store.put_section("fx", {"rate": "85"}, source_url="https://example.test", fetched_at="2026-01-01T00:00:00Z")
    section = store.section("fx")
    assert section is not None
    assert section["status"] == "ok"
    assert section["data"] == {"rate": "85"}
    assert section["source_url"] == "https://example.test"


def test_section_reads_are_isolated_copies() -> None:
    store = SnapshotStore()
    store.put_section("gold", {"price": "2000"})
    first = store.section("gold")
    first["data"]["price"] = "TAMPERED"
    second = store.section("gold")
    assert second["data"]["price"] == "2000"


def test_put_error_retains_last_known_data() -> None:
    store = SnapshotStore()
    store.put_section("bars", {"count": 5})
    store.put_error("bars", "rate_limited", "too many requests")
    section = store.section("bars")
    assert section["status"] == "error"
    assert section["error"] == {"code": "rate_limited", "message": "too many requests"}
    assert section["data"] == {"count": 5}


def test_providers_and_meta() -> None:
    store = SnapshotStore()
    store.put_provider("goldprice.dev", {"id": "goldprice.dev", "status": "available"})
    store.put_section("gold", {"price": "2000"})
    store.mark_cycle()
    meta = store.meta()
    assert meta["cycle_count"] == 1
    assert "gold" in meta["sections"]
    assert store.providers()[0]["id"] == "goldprice.dev"
    assert "updated_at_utc" in store.providers()[0]


def test_missing_section_returns_none() -> None:
    assert SnapshotStore().section("news") is None


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    state = tmp_path / "published" / "snapshot.v1.json"
    store = SnapshotStore(state_path=state)
    store.put_section("gold", {"price": "2000"})
    store.put_provider("frankfurter", {"id": "frankfurter", "status": "available"})
    store.mark_cycle()
    store.save()
    assert state.is_file()

    reloaded = SnapshotStore(state_path=state)
    assert reloaded.load() is True
    assert reloaded.section("gold")["data"] == {"price": "2000"}
    assert reloaded.meta()["cycle_count"] == 1


def test_load_without_file_returns_false(tmp_path: Path) -> None:
    store = SnapshotStore(state_path=tmp_path / "nope.json")
    assert store.load() is False
