#!/usr/bin/env python3
"""Minimal client showing how to consume the Gold API from another app.

Usage:
    GOLD_API_URL=https://your-service.up.railway.app python3 scripts/client_example.py
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = os.getenv("GOLD_API_URL", "http://localhost:8000").rstrip("/")


def get(path: str) -> dict:
    url = f"{BASE}{path}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def main() -> int:
    health = get("/health")
    print(f"health: {health['status']}  sections={health['sections_ready']}")

    gold = get("/api/v1/gold")
    spot = gold["gold"]["data"]
    print(f"gold USD/oz : {spot['price_usd_per_troy_ounce']}  (stale={spot['is_stale']})")
    print(f"gold USD/g  : {spot['price_usd_per_gram']}")

    derived = gold.get("derived", {}).get("gold_reference_inr_per_gram")
    if derived:
        print(f"gold INR/g  : {derived['value']}  ({derived['calculation']})")

    fx = get("/api/v1/fx")
    print(f"USD/INR     : {fx['data']['rate']}  (effective {fx['data']['effective_date']})")

    providers = get("/api/v1/providers")["providers"]
    print("providers:")
    for entry in providers:
        print(f"  - {entry['id']:20s} {entry['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
