## Summary

<!-- What does this PR change and why? Link any related issue. -->

Closes #

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] New provider
- [ ] Documentation
- [ ] Refactor / internal
- [ ] CI / tooling

## How has this been tested?

<!-- Describe the tests you ran. Include commands and results. -->

```bash
ruff check .
pytest -q
```

## Checklist

- [ ] The change is focused and does not mix unrelated edits.
- [ ] `ruff check .` passes.
- [ ] `pytest -q` passes.
- [ ] New behaviour is covered by hermetic tests (no network).
- [ ] The data layer (`app/providers`, engine) stays standard-library only.
- [ ] Docs (README / CHANGELOG / docs) are updated where relevant.
- [ ] No secrets, tokens or real credentials are included.
