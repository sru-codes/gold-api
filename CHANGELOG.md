# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- README artwork: `assets/banner.svg`, `assets/logo.svg` and an always-rendering
  `assets/architecture.svg` system diagram (SVG, no external fonts).

## [1.0.0] - 2026-10-15

### Added

- Initial public release of the `gold-api` self-hosted market-data service.
- 60-second scheduler with per-source cadences and a forced first cycle.
- Read-only JSON API under `/api/v1`: `snapshot`, `gold`, `fx`, `bars`,
  `macro`, `news`, `providers`, plus `/health` and OpenAPI docs at `/docs`.
- Providers: goldprice.dev (keyless XAU/USD spot + daily bars), Frankfurter
  (USD/INR reference FX), and optional FRED (macro) and GNews (news) adapters.
- In-process derived view including `gold_reference_inr_per_gram`.
- Provider health reporting and `LIVE`/`PARTIAL`/`DEGRADED` service modes.
- Thread-safe snapshot store with atomic disk persistence.
- Bounded-retry JSON HTTP client with auditable disk caching.
- Optional bearer-token protection for `POST /api/v1/refresh`.
- Dockerfile and `railway.json` for one-service deployment; `PORT`-aware.
- Unit tests (hermetic), CI workflow, and contributor/security documentation.

### Fixed

- First-cycle scheduling on freshly booted hosts: sources that had never run are
  now always due, instead of being skipped when `time.monotonic()` is small.
- `POST /api/v1/refresh` no longer fails when called (keyword-only `force`).
- Disk-cache reads and writes are best-effort; a read-only or missing volume no
  longer aborts a refresh cycle.
- Removed the Dockerfile `VOLUME` directive, which Railway rejects.

[Unreleased]: https://github.com/sru-codes/gold-api/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/sru-codes/gold-api/releases/tag/v1.0.0
