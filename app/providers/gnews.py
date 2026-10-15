"""Optional GNews context adapter; news never enters quantitative signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from .base import JsonHttpClient, ProviderError


@dataclass(frozen=True)
class NewsArticle:
    title: str
    url: str
    published_at_utc: datetime
    source_name: str
    description: str | None


class GNewsAdapter:
    BASE_URL = "https://gnews.io/api/v4"

    def __init__(self, client: JsonHttpClient, api_key: str | None):
        self.client = client
        self.api_key = api_key

    def search(self, query: str, start: datetime, end: datetime, *, maximum: int = 10) -> tuple[NewsArticle, ...]:
        if not self.api_key:
            raise ProviderError("gnews", "missing_credentials", "GNEWS_API_KEY is required")
        if end < start or not 1 <= maximum <= 10:
            raise ValueError("invalid date range or free-tier maximum")
        params = {
            "q": query,
            "lang": "en",
            "max": str(maximum),
            "from": start.isoformat(),
            "to": end.isoformat(),
            "apikey": self.api_key,
        }
        url = f"{self.BASE_URL}/search?{urlencode(params)}"
        fetched = self.client.get_json(
            url,
            ttl_seconds=900,
            auth_scope="authenticated",
            display_url=f"{self.BASE_URL}/search?q={query}&apikey=REDACTED",
        )
        rows = fetched.payload.get("articles") if isinstance(fetched.payload, dict) else None
        if not isinstance(rows, list):
            raise ProviderError("gnews", "invalid_schema", "Expected articles array")
        articles = []
        for row in rows:
            try:
                published = datetime.fromisoformat(str(row["publishedAt"]).replace("Z", "+00:00"))
                source_name = str(row["source"]["name"])
                article = NewsArticle(str(row["title"]), str(row["url"]), published, source_name, row.get("description"))
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError("gnews", "invalid_schema", "Invalid article response") from exc
            if published > end:
                raise ProviderError("gnews", "future_observation", "Article was published after requested cutoff")
            articles.append(article)
        articles.sort(key=lambda item: item.published_at_utc)
        return tuple(articles)
