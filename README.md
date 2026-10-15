# gold-api

A small, self-hosted market-data API. It pulls gold spot, USD/INR reference FX,
daily gold bars, and optional macro/news context on a schedule — by default
**every 60 seconds** — assembles one snapshot, and serves it as plain JSON that
any downstream app (including your main repo) can consume.

- **No API keys required.** Every upstream source it uses is keyless.
- **Railway-ready.** One Dockerfile, one service, `/health` healthcheck.
- **Zero-downtime providers.** A failing source degrades one section; it never
  takes the service down. Per-provider health is always exposed.

## Data sources

| Section  | Source | Auth | Cadence |
|----------|--------|------|---------|
| `gold`   | [goldprice.dev](https://goldprice.dev) `XAU-USD-SPOT` | optional key | 60s |
| `fx`     | [Frankfurter](https://frankfurter.dev) USD/INR | none | 300s |
| `bars`   | goldprice.dev daily bars | optional key | 3600s |
| `macro`  | [FRED](https://fred.stlouisfed.org) | optional `FRED_API_KEY` | 3600s |
| `news`   | [GNews](https://gnews.io) | optional `GNEWS_API_KEY` | 900s |
| `derived`| computed | — | every snapshot |

`derived.gold_reference_inr_per_gram` is calculated as
`XAU/USD per troy ounce ÷ 31.1034768 × USD/INR`. It is a contextual reference,
not an exchange settlement or an executable price.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | service metadata + endpoint index |
| GET | `/health` | liveness, section readiness, last refresh (Railway healthcheck) |
| GET | `/api/v1/snapshot` | **everything** in one payload |
| GET | `/api/v1/gold` | gold spot (USD/oz, USD/g) + derived INR/gram |
| GET | `/api/v1/fx` | USD/INR reference rate |
| GET | `/api/v1/bars` | daily gold bars |
| GET | `/api/v1/macro` | FRED series (if configured) |
| GET | `/api/v1/news` | dated news context (if configured) |
| GET | `/api/v1/providers` | per-provider health |
| POST | `/api/v1/refresh` | force a refresh (bearer token if `ADMIN_TOKEN` is set) |
| GET | `/docs` | interactive OpenAPI docs |

Sections that have not produced data yet return **503** with a clear message;
`/health` reports `status: "starting"` until the first cycle lands.

## Quick start (local)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                     # optional; defaults work as-is
uvicorn app.main:app --reload --port 8000
```

Then:

```bash
curl -s localhost:8000/health | jq
curl -s localhost:8000/api/v1/snapshot | jq
curl -s localhost:8000/api/v1/gold | jq '.derived'
```

## Deploy to Railway

1. Create a Railway project and add a service from this GitHub repo.
2. Railway detects the root `Dockerfile` automatically.
3. **Attach a volume mounted at `/data`** so the provider cache and the last
   published snapshot survive redeploys.
4. (Optional) set service variables:
   - `ADMIN_TOKEN` — long random secret; protects `POST /api/v1/refresh`.
     Generate with `openssl rand -hex 32`.
   - `GOLDPRICE_API_KEY`, `FRED_API_KEY`, `GNEWS_API_KEY` — only for higher
     limits or the optional macro/news sections.
   - `CORS_ORIGINS` — e.g. `https://your-app.up.railway.app` (defaults to `*`).
5. Generate a public domain and verify:
   `https://<your-domain>/health` and `https://<your-domain>/api/v1/snapshot`.

Railway injects `PORT`; the image forwards it to uvicorn.

## Consuming it from another app

```python
import os, urllib.request, json

BASE = os.getenv("GOLD_API_URL", "https://gold-api-production.up.railway.app")

with urllib.request.urlopen(f"{BASE}/api/v1/gold", timeout=10) as r:
    payload = json.load(r)

spot = payload["gold"]["data"]["price_usd_per_troy_ounce"]
inr_per_gram = payload["derived"]["gold_reference_inr_per_gram"]["value"]
print(spot, inr_per_gram)
```

Browsers can call it directly (CORS is enabled by default). See
`scripts/client_example.py` for a fuller example.

## How the refresh works

- A background task runs on a loop (`REFRESH_INTERVAL_SECONDS`, default 60).
- Each source has its own interval; the fast spot price refreshes every cycle,
  slower sources on their own cadence.
- Every upstream response is also cached to disk under `CACHE_DIR`, so a
  transient network failure reuses a recent observation instead of losing data.
- The assembled snapshot is persisted to `DATA_DIR/published/snapshot.v1.json`
  and reloaded on boot, so a restart does not start empty.
- HTTP handlers read from memory only and never block on a provider call.

## Configuration

See `.env.example` for the full list. Everything is optional with safe defaults.

## Notes and limits

- goldprice.dev keyless is rate-limited (10 req/min, 100 req/hour) and the price
  is 15 minutes delayed. Free commercial use requires visible goldprice.dev
  attribution. Set `GOLDPRICE_API_KEY` for higher limits.
- Frankfurter rates are reference mid-market/blended observations, not
  executable FX quotes.
- FRED and GNews sections are context only and never feed a quantitative signal.
- This service does not automate exchange data (e.g. MCX exports); it reports
  international reference data.

## License

MIT — see [LICENSE](LICENSE).
