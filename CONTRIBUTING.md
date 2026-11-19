# Contributing

## Development principles

This project handles financial-account data and order execution. Changes must prioritize deterministic behavior, auditability, and fail-safe defaults.

1. Keep live trading disabled.
2. Keep the Trading 212 demo API restriction.
3. Do not weaken risk checks to make tests pass.
4. Do not let model output directly authorize an order.
5. Add regression tests for safety-relevant bug fixes.
6. Mock network services in unit tests.
7. Never include credentials, account identifiers, personal data, or execution-state files in commits.

## Branches

Create a branch from an up-to-date `main`:

```bash
git switch main
git pull --ff-only
git switch -c feature/short-description
```

Use prefixes `feature/`, `fix/`, `test/`, `docs/`, or `chore/`.

## Commit messages

Follow Conventional Commits:

```text
<type>: <imperative summary>
```

Common types: `feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `chore`, and `build`.

Examples:

- `feat: add max daily loss limit`
- `fix: block orders with stale prices`
- `test: cover ambiguous order timeout`
- `docs: explain demo environment setup`

## Before opening a pull request

Run:

```bash
PYTHONPATH=. python -m pytest -v
git status --short
git diff --check
```

Review staged changes for secrets and generated files. Do not blindly run `git add .` when local credentials, state, logs, or generated files may exist.

## Pull request checklist

- [ ] The change has a clear, limited scope.
- [ ] Tests cover intended behavior and relevant failure paths.
- [ ] All tests pass locally.
- [ ] No credentials, personal data, logs, or generated files are included.
- [ ] Dry-run and demo-only safeguards remain intact.
- [ ] Ambiguous order outcomes fail closed.
- [ ] Documentation is updated where behavior or setup changed.
