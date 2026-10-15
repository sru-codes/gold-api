#!/usr/bin/env python3
"""Offline smoke test: exercise the refresh engine without starting a server.

Runs one full refresh against the live upstream sources and prints the assembled
snapshot summary. Useful locally and as a CI sanity check.

    python3 scripts/smoke_test.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.refresh import RefreshEngine  # noqa: E402
from app.store import SnapshotStore  # noqa: E402


def main() -> int:
    import tempfile
    from dataclasses import replace

    with tempfile.TemporaryDirectory() as tmp:
        settings = replace(Settings.from_env(), data_dir=tmp, cache_dir=f"{tmp}/cache")
        store = SnapshotStore(state_path=Path(tmp) / "published" / "snapshot.v1.json")
        engine = RefreshEngine(settings, store)
        engine.refresh_all(force=True)
        snapshot = engine.build_snapshot()

    print(f"mode: {snapshot['mode']}")
    for name, section in snapshot["sections"].items():
        if section is None:
            print(f"  {name:8s} MISSING")
            continue
        status = section.get("status")
        detail = section.get("error") or section.get("data")
        if isinstance(detail, dict):
            detail = {k: v for k, v in detail.items() if k in ("price_usd_per_gram", "rate", "count", "note")} or "ok"
        print(f"  {name:8s} {status:6s} {detail}")
    print("providers:")
    for entry in snapshot["providers"]:
        print(f"  - {entry['id']:22s} {entry['status']}")
    print(json.dumps(snapshot["derived"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
