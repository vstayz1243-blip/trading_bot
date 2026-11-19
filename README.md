# Trading Bot

A Python algorithmic-trading project combining market data, technical analysis, portfolio analysis, risk checks, and a decision agent. The current integration targets the **Trading 212 demo API** and uses a local **Ollama** instance for language-model inference.

> **Safety:** The current bot configuration is deliberately fail-safe: `DRY_RUN = True` and `DEMO_ORDERS_ENABLED = False`. Do not change these settings as part of routine testing. This project is not financial advice and has not been validated for unattended or live-money trading.

## Architecture

| Area | Responsibility |
|---|---|
| `client/` | Trading 212 API client, positions, history, and API exceptions |
| `trading212/` | Trading 212 API-related modules |
| `services/` | Market data, technical indicators, portfolio metrics, and stop-loss verification |
| `agents/` | Technical, risk, portfolio, and orchestration agents; Ollama client |
| `strategy/` | Trading decision and deterministic risk-management logic |
| `execution/` | Order execution safeguards and persistent execution state |
| `models/` | Market-data and position models |
| `bot/` | Main bot orchestration |
| `test/` | Automated unit and safety tests |

### Processing flow

1. Retrieve account, position, instrument, and market data.
2. Calculate technical indicators and portfolio metrics.
3. Run the analysis agents through the orchestrator.
4. Produce a trading decision.
5. Apply deterministic risk limits and stop-loss checks.
6. Keep execution in dry-run mode.

Language-model output is advisory. Deterministic validation in the strategy and execution layers must remain authoritative.

## Requirements

- Python 3.14 (the development version currently in use)
- Git
- Ollama running locally with the configured model, currently `qwen3:8b`
- Trading 212 demo API credentials for account-connected runs

## Setup

### 1. Clone

```bash
git clone https://github.com/vstayz1243-blip/trading_bot.git
cd trading_bot
```

### 2. Create a virtual environment

macOS / Linux:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure credentials locally

Create `credentials.json` in the repository root:

```json
{
  "key": "YOUR_TRADING212_DEMO_API_KEY",
  "secret": "YOUR_TRADING212_DEMO_API_SECRET"
}
```

This file is ignored by Git. Never commit real API credentials, account data, tokens, or secrets. Use demo credentials only.

### 5. Start Ollama

```bash
ollama pull qwen3:8b
ollama list
```

The current agent configuration connects to `http://localhost:11434`.

## Run

Start the bot from the repository root:

```bash
python main.py
```

The current entry point uses ticker `AAPL_US_EQ` and a 300-second interval.

Do not run account-connected scripts unless you understand which API endpoints they call. Distinguish read-only diagnostics from scripts that can place or modify orders.

## Tests

```bash
PYTHONPATH=. python -m pytest -v
```

Default pytest discovery is scoped to `test/`. This deliberately excludes root-level and Ollama-local scripts that may require a running service, credentials, or external API access.

Unit tests should mock external services. CI must never require Trading 212 credentials, connect to a real account, or submit orders.

## Safety invariants

- Keep the API base URL restricted to the Trading 212 demo environment.
- Keep dry-run enabled by default.
- Keep demo order execution disabled by default.
- Never let an LLM response bypass deterministic risk validation.
- Do not automatically retry a write request when its execution status may be unknown.
- Preserve persistent execution locks when an order outcome is ambiguous.
- Require explicit reconciliation and manual review before clearing an uncertain execution state.
- Never store credentials or runtime execution state in Git.

## Development workflow

Use short-lived branches and pull requests:

- `feature/<short-description>` — new functionality
- `fix/<short-description>` — bug fixes
- `test/<short-description>` — tests
- `docs/<short-description>` — documentation
- `chore/<short-description>` — maintenance

Use Conventional Commits, for example:

- `feat: add portfolio exposure limit`
- `fix: reject stale market data`
- `test: cover stop-loss reconciliation`
- `docs: describe local setup`
- `chore: update CI dependencies`

See [CONTRIBUTING.md](CONTRIBUTING.md).
