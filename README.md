# Risk-Controlled SPY Market Intelligence and Paper-Trading System

`spy-market-agent` is an educational Python 3.12 project for researching SPY daily
signals, evaluating leakage-aware machine-learning baselines, running risk-controlled
long-or-cash backtests, persisting audit artifacts in SQLite, and preparing explicitly
approved Alpaca paper orders behind fail-closed safety gates.

It is experimental research software. It is not investment advice, does not claim
profitability, and is not real-money trading infrastructure.

## Version 1 Status

Version 1.0.0 covers the completed Phase 1 through Phase 8 implementation plus the Phase 9
documentation and release-readiness work:

- SPY ETF only.
- Daily OHLCV data only.
- Long-or-cash positions only.
- No short selling, leverage, margin, fractional-share orders, or additional markets.
- Provider-independent market-data contracts and validation, but no market-data downloader.
- Leakage-safe trailing features and the approved open `t + 1` to open `t + 6` label.
- Chronological train, validation, and final-test design with gap-aware split contracts.
- Deterministic logistic-regression and gradient-boosting baselines.
- Validation-only model selection and locked final-test evaluation.
- Fixed long-or-cash signal policy and next-open execution mapping.
- Independent risk checks before every backtest fill.
- In-memory backtesting with transaction costs, slippage, cash, shares, equity, drawdown,
  turnover, fills, orders, and risk-decision audit frames.
- Explicit SQLite initialization and persistence for validated research artifacts.
- Read-only FastAPI routes for persisted data status, model evaluations, backtests, and
  local paper-execution status.
- Read-only Streamlit dashboard views backed by the FastAPI client.
- Explicitly invoked Alpaca paper-only execution service for SPY whole-share market DAY
  orders, with no API or dashboard submission controls.

## Safety Boundaries

Live trading is not supported. `EXECUTION_MODE` may only be `paper`, and any attempt to
configure `live` must fail. The committed defaults cannot submit an order:

- no live trading
- no automatic paper-order submission
- `ENABLE_PAPER_EXECUTION=false`
- `DRY_RUN=true`
- `PAPER_EXECUTION_KILL_SWITCH=true`
- the durable SQLite paper-execution kill switch defaults to engaged

Paper execution requires all of the following through an explicit service call, not through
application startup, FastAPI, or Streamlit:

- paper mode, paper execution enabled, dry-run disabled, and configuration kill switch off
- durable SQLite kill switch off with explicit confirmation and audit reason
- Alpaca paper credentials supplied through runtime configuration
- canonical Alpaca paper endpoint identity: `https://paper-api.alpaca.markets`
- `TradingClient(..., paper=True)` constructed only when the adapter is explicitly created
- a risk-approved immutable `ProposedOrder`
- a deterministic `PaperOrderInstruction` fingerprint
- a human `PaperOrderApproval` bound to the exact signal ID, client-order ID, and fingerprint
- execution-time risk re-evaluation
- regular market hours on the instruction execution session
- no stale or expired signal
- unique signal ID, client-order ID, and approval ID
- at most one SPY paper-execution reservation per execution session

Timeouts, transport uncertainty, contradictory broker responses, and broker acceptance
followed by local ledger failure are recorded as `submission_unknown`. The system does not
retry automatically. Reconciliation is lookup-only by `client_order_id` and never submits a
new order.

## Not Implemented

Version 1 intentionally does not include:

- market-data downloading
- real-time data feeds
- investment recommendations
- profitability claims
- probability calibration or threshold optimization
- hyperparameter tuning or model binary persistence
- API write routes
- dashboard execution controls
- automatic broker communication
- automatic paper-order submission
- order cancellation, replacement, liquidation, stops, limits, brackets, OCO, or OTO
- schedulers, workers, cron jobs, deployment files, or cloud infrastructure
- live trading or live Alpaca endpoints
- assets other than SPY

## Quick Start

Use Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the complete verification gate:

```bash
pytest --cov-fail-under=85
ruff check .
ruff format --check .
mypy src tests
```

Initialize a local SQLite database explicitly:

```bash
python -c "from spy_market_agent.persistence import initialize_database; initialize_database('./spy_market_agent.sqlite3')"
```

Start the read-only FastAPI application:

```bash
python -m uvicorn "spy_market_agent.api.main:create_app" --factory --host 127.0.0.1 --port 8000
```

Start the read-only Streamlit dashboard:

```bash
streamlit run src/spy_market_agent/dashboard/streamlit_app.py
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Reproducibility](docs/REPRODUCIBILITY.md)
- [Workflows](docs/WORKFLOWS.md)
- [Security and Safety](docs/SECURITY_AND_SAFETY.md)
- [Demo Guide](docs/DEMO_GUIDE.md)
- [Portfolio Overview](docs/PORTFOLIO_OVERVIEW.md)
- [Project Specification](PROJECT_SPEC.md)
- [Changelog](CHANGELOG.md)
- [Version 1.0.0 Release Notes](RELEASE_NOTES_V1.0.0.md)
- [Version 1 Release Checklist](VERSION_1_RELEASE_CHECKLIST.md)

## Read-Only API Routes

The FastAPI application exposes only GET routes:

```text
GET /health
GET /api/v1/data/status
GET /api/v1/model-runs
GET /api/v1/model-runs/{run_id}
GET /api/v1/model-runs/{run_id}/predictions
GET /api/v1/backtests
GET /api/v1/backtests/{run_id}
GET /api/v1/backtests/{run_id}/equity
GET /api/v1/backtests/{run_id}/orders
GET /api/v1/backtests/{run_id}/risk-decisions
GET /api/v1/backtests/{run_id}/fills
GET /api/v1/paper-trading/status
GET /api/v1/paper-orders
GET /api/v1/paper-orders/{client_order_id}
```

The API and dashboard never approve orders, submit orders, reconcile orders, change kill
switches, cancel orders, replace orders, or construct an Alpaca client.

## Quality Policy

The repository uses:

- Pytest with branch coverage enabled.
- Required full-suite coverage gate: `pytest --cov-fail-under=85`.
- Ruff linting: `ruff check .`.
- Ruff formatting check: `ruff format --check .`.
- MyPy strict checks over `src` and `tests`: `mypy src tests`.
- Warning policy: unexpected warnings fail by default. The only allowed warning filters are
  exact documented upstream dependency warnings in `pyproject.toml`.

The current deterministic tests use synthetic or in-memory data. No committed real SPY
dataset, generated SQLite database, private screenshot, account identifier, or credential is
required.
