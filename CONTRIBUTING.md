# Contributing to gold-api

Thanks for your interest in improving `gold-api`. This document explains how to
set up a development environment, the standards we hold contributions to, and
how to get a change merged.

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

```bash
git clone https://github.com/sru-codes/gold-api.git
cd gold-api

python3 -m venv .venv
. .venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt
```

Run the service with auto-reload:

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: <http://localhost:8000/docs>.

## Project principles

1. **The data layer stays dependency-free.** `app/providers/*` and the core
   engine use only the standard library. The only runtime dependencies are
   FastAPI and uvicorn, for the web layer.
2. **No network in tests.** Tests inject a fake transport and run offline.
3. **No silent fabrication.** Never forward-fill, guess, or invent a value to
   hide a provider failure. Record the error and degrade.
4. **Provenance is part of the payload.** Every value should be attributable to
   a source with a timestamp.

## Making changes

1. Fork the repository and create a branch:
   `git checkout -b feat/short-description`.
2. Make focused changes. Prefer small, reviewable commits.
3. Add or update tests.
4. Run the checks below and make sure they pass.
5. Open a pull request using the template.

### Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add silver spot provider
fix: correct first-cycle scheduling on fresh hosts
docs: expand deployment notes
chore: bump uvicorn
```

### Checks

```bash
ruff check .     # lint
pytest -q        # tests
```

### Adding a provider

1. Add `app/providers/<name>.py` with a strict schema validator that raises
   `ProviderError` on any unexpected shape.
2. Wire it into `RefreshEngine` with its own interval and a
   `store.put_provider(...)` health record.
3. Add a unit test with a fake transport covering both a valid and an invalid
   payload.
4. Document it in the README data-sources table.

## Pull request checklist

- [ ] The change is focused and described in the PR template.
- [ ] `ruff check .` passes.
- [ ] `pytest -q` passes.
- [ ] New behaviour is covered by tests.
- [ ] Docs (README/`docs`) updated where relevant.
- [ ] No secrets, tokens or real credentials are committed.

## Reporting bugs and requesting features

Use the issue templates. For anything security-related, follow
[SECURITY.md](SECURITY.md) instead of opening a public issue.
