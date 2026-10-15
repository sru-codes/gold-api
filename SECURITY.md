# Security Policy

## Supported versions

This project is pre-1.0 in spirit but versioned semantically. Security fixes are
issued against the latest release on `main`.

| Version | Supported |
|---------|-----------|
| 1.x     | ✅        |
| < 1.0   | ❌        |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately using GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository (**Security → Report a vulnerability**). If you cannot use
that, open a minimal public issue that asks for a private channel without
disclosing details.

Please include:

- a description of the issue and its impact,
- steps to reproduce (a proof of concept if possible),
- affected version / commit,
- any suggested remediation.

### What to expect

| Stage | Target |
|-------|--------|
| Acknowledgement | within 3 business days |
| Initial assessment | within 7 business days |
| Fix or mitigation plan | within 30 days for confirmed issues |

We will credit reporters in the release notes unless you ask to remain anonymous.

## Scope

In scope:

- the `gold-api` service (`app/`), its HTTP surface and data handling,
- the Docker image and deployment defaults in this repository,
- handling of credentials and configuration.

Out of scope:

- vulnerabilities in upstream providers (goldprice.dev, Frankfurter, FRED,
  GNews) — report those to the respective vendor,
- issues that require a already-compromised host or a malicious operator with
  root on the deployment,
- denial of service through sheer request volume against a service you run
  without rate limiting (see the hardening checklist).

## Security design of this project

- **No secrets in the repository.** Only `.env.example` (empty placeholders) is
  committed. `.env`, `data/` and cache directories are git-ignored.
- **Provider credentials stay server-side.** `GOLDPRICE_API_KEY`,
  `FRED_API_KEY` and `GNEWS_API_KEY` are read from the environment, used only in
  outbound requests, and redacted in any logged URL (`api_key=REDACTED`).
- **Optional write protection.** `POST /api/v1/refresh` is gated by a
  constant-time bearer check when `ADMIN_TOKEN` is set:
  `hmac.compare_digest`. All read endpoints are intentionally public and
  read-only.
- **No request-path network calls.** HTTP handlers only read an in-memory
  snapshot, so user requests cannot be used to pivot to upstreams or to amplify
  load.
- **Bounded retries and backoff** on outbound calls limit accidental
  self-inflicted load and provider throttling.
- **Best-effort local state.** Cache and snapshot writes are atomic and never
  block or crash collection.

## Deployment hardening checklist

- [ ] Set a strong `ADMIN_TOKEN` (`openssl rand -hex 32`) or leave the refresh
      endpoint unavailable to the public.
- [ ] Restrict `CORS_ORIGINS` to the exact origins that need the API instead of
      leaving it `*`.
- [ ] Attach a persistent volume at `/data` and make sure it is not world
      readable.
- [ ] Put the service behind a reverse proxy / platform that terminates TLS.
- [ ] If the API is sensitive to you, add rate limiting and/or authentication at
      the edge — this service does not implement user auth by design.
- [ ] Rotate any provider keys you configure, and never paste tokens into issue
      trackers, chat logs or commit messages.
- [ ] Keep the base image and dependencies patched (`docker pull`, `pip install -U`).

## Known limitations

- The API is unauthenticated for reads. Do not expose data you consider
  confidential.
- External provider content (news headlines, macro values) is untrusted input;
  it is returned as data and must not be rendered as HTML without escaping.
- Timestamps and prices are provided for analysis; they are not an executable
  market feed and carry no availability guarantee.
