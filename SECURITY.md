# Security Policy

## Supported version

Security fixes should target the current default branch, `main`.

## Reporting a vulnerability

Do not publish API keys, credentials, account data, execution-state files, or details that could enable unauthorized trading in a public issue.

Use GitHub private vulnerability reporting for this repository if enabled. Otherwise, contact the repository owner privately.

## Credential handling

- Use Trading 212 demo credentials for development.
- Keep `credentials.json` local; it is ignored by Git.
- Never paste secrets into issues, pull requests, logs, or source files.
- If a credential is committed or exposed, revoke or rotate it immediately. Removing a file in a later commit does not remove it from Git history.
- Treat exposed API keys as compromised, even if the repository is later made private.

## Trading safety

- The application is currently intended for demo-environment testing.
- Dry-run must remain enabled by default.
- Demo order execution must remain disabled by default.
- Do not enable live-money trading without a separate security, operational, and risk review.
- Ambiguous order outcomes must not trigger automatic resubmission.
