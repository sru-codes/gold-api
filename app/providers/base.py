"""Small JSON HTTP client with bounded retries and auditable disk caching."""

from __future__ import annotations

import hashlib
import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


class ProviderError(RuntimeError):
    def __init__(self, provider: str, code: str, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.status = status
        self.retryable = retryable


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class FetchResult:
    payload: Any
    source_url: str
    retrieved_at_utc: str
    cache_status: str
    http_status: int


Transport = Callable[[str, Mapping[str, str], float], TransportResponse]


def urllib_transport(url: str, headers: Mapping[str, str], timeout: float) -> TransportResponse:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return TransportResponse(response.status, dict(response.headers.items()), response.read())
    except urllib.error.HTTPError as exc:
        return TransportResponse(exc.code, dict(exc.headers.items()), exc.read())


class JsonHttpClient:
    def __init__(
        self,
        provider: str,
        cache_dir: str | Path,
        *,
        transport: Transport = urllib_transport,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        max_retries: int = 2,
        base_backoff_seconds: float = 0.25,
        timeout_seconds: float = 10.0,
    ):
        if max_retries < 0 or base_backoff_seconds < 0 or timeout_seconds <= 0:
            raise ValueError("invalid HTTP client retry configuration")
        self.provider = provider
        self.cache_dir = Path(cache_dir)
        self.transport = transport
        self.sleeper = sleeper
        self.clock = clock
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.timeout_seconds = timeout_seconds

    def _cache_key(self, url: str, auth_scope: str) -> str:
        return hashlib.sha256(f"{url}\n{auth_scope}".encode()).hexdigest()

    def _cache_path(self, url: str, auth_scope: str) -> Path:
        return self.cache_dir / self.provider / f"{self._cache_key(url, auth_scope)}.json"

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        ttl_seconds: int = 0,
        auth_scope: str = "anonymous",
        display_url: str | None = None,
    ) -> FetchResult:
        public_url = display_url or url
        path = self._cache_path(url, auth_scope)
        now = self.clock()
        if ttl_seconds > 0 and path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, KeyError, ValueError):
                cached = None
            if cached is not None and now - float(cached["cached_at_epoch"]) <= ttl_seconds:
                return FetchResult(
                    cached["payload"], public_url, cached["retrieved_at_utc"], "hit", cached["http_status"]
                )

        request_headers = {"Accept": "application/json", "User-Agent": "GoldAPI/1.0 (+https://github.com/sru-codes/gold-api)"}
        request_headers.update(headers or {})
        last_error: ProviderError | None = None
        for attempt in range(self.max_retries + 1):
            response: TransportResponse | None = None
            try:
                response = self.transport(url, request_headers, self.timeout_seconds)
            except (TimeoutError, OSError) as exc:
                last_error = ProviderError(self.provider, "network_error", str(exc), retryable=True)
            else:
                if 200 <= response.status < 300:
                    try:
                        payload = json.loads(response.body.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise ProviderError(self.provider, "invalid_json", "Provider returned invalid JSON") from exc
                    retrieved_at = datetime.fromtimestamp(now, timezone.utc).isoformat().replace("+00:00", "Z")
                    cached = {
                        "provider": self.provider,
                        "source_url": public_url,
                        "retrieved_at_utc": retrieved_at,
                        "cached_at_epoch": now,
                        "http_status": response.status,
                        "payload": payload,
                    }
                    # Persisting the cache is a convenience; a read-only or
                    # unmounted volume must never break data collection.
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps(cached, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    except OSError:
                        pass
                    return FetchResult(payload, public_url, retrieved_at, "miss", response.status)
                retryable = response.status == 429 or 500 <= response.status < 600
                code = "rate_limited" if response.status == 429 else "authentication_failed" if response.status in (401, 403) else "http_error"
                last_error = ProviderError(
                    self.provider,
                    code,
                    f"{self.provider} returned HTTP {response.status}",
                    status=response.status,
                    retryable=retryable,
                )
                if not retryable:
                    raise last_error
            if attempt < self.max_retries:
                retry_after = None
                if response is not None and response.status == 429:
                    try:
                        retry_after = min(30.0, max(0.0, float(response.headers.get("Retry-After", ""))))
                    except ValueError:
                        retry_after = None
                delay = retry_after if retry_after is not None else self.base_backoff_seconds * (2 ** attempt) + random.Random(attempt).uniform(0, self.base_backoff_seconds / 4)
                self.sleeper(delay)
        assert last_error is not None
        raise last_error
