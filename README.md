# Risk-Controlled SPY Market Intelligence and Paper-Trading System

This project is a Python research scaffold for studying SPY market signals, evaluating future machine-learning baselines, running future historical backtests, and eventually preparing paper-only order submission behind independent risk controls.

The project is educational and experimental. It is not investment advice, and it must never claim or guarantee profitability.

## Status

Current development status: Phase 3 configuration, canonical schema, and validation.

The repository currently contains typed configuration, paper-only configuration validation, a provider-independent daily SPY schema, an XNYS calendar adapter, deterministic dataset checksums, data-quality validation, and tests. Market downloading, model training, recommendations, backtesting, order submission, and broker communication are not implemented.

## Version 1 Scope

- Python 3.12.
- SPY ETF only.
- Daily OHLCV market-data validation.
- Long-or-cash positions only.
- No short selling.
- No leverage.
- Historical backtesting in later phases.
- Initial simulated capital of USD 10,000.
- Logistic regression baseline and gradient boosting comparison in later phases.
- FastAPI backend and Streamlit dashboard in later phases.
- SQLite persistence in later phases.
- Alpaca paper trading only in a later phase, after explicit approval.

## Safety Restrictions

- Live-money trading is not supported.
- `EXECUTION_MODE` may only be `paper`.
- Any request for live execution must raise `RuntimeError` in future configuration code.
- `ENABLE_PAPER_EXECUTION` defaults to `false`.
- `DRY_RUN` defaults to `true`.
- Application startup must not submit paper orders.
- The package import does not load settings or perform external actions.
- Models must never communicate directly with brokers.
- All future proposed trades must pass through an independent risk-management layer.
- Version 1 must not permit short selling, leverage, or non-SPY assets.

## Repository Structure

```text
src/spy_market_agent/      Python package source
src/spy_market_agent/config/       Typed settings
src/spy_market_agent/market_data/  Canonical request, batch, checksum, calendar, and provider protocol
src/spy_market_agent/validation/   Canonical SPY daily OHLCV validation
tests/unit/                Unit tests
tests/integration/         Integration tests
tests/fixtures/            Deterministic test fixtures
data/raw/                  Ignored downloaded raw data
data/processed/            Ignored processed datasets
artifacts/models/          Ignored generated model artifacts
artifacts/reports/         Ignored generated reports
PROJECT_SPEC.md            Approved project specification
AGENTS.md                  Permanent instructions for future Codex tasks
```

## Python Requirement

Use Python 3.12. The project metadata requires:

```text
>=3.12,<3.13
```

## Setup

Create and activate a Python 3.12 virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Do not create a real `.env` file with credentials for Phase 3. Use `.env.example` only as a placeholder reference. Alpaca integration is not implemented.

## Implemented Phase 3 Capabilities

- Typed settings via Pydantic Settings.
- Paper-only configuration validation.
- Secret-aware optional future Alpaca credential fields.
- Provider-independent daily SPY market-data request, metadata, and batch models.
- Provider protocol for deterministic fake providers and future vendor adapters.
- XNYS trading-session calendar adapter using `exchange-calendars`.
- Canonical adjusted daily SPY OHLCV DataFrame schema.
- Deterministic SHA-256 dataset checksums.
- Deterministic validation of sessions, column schema, OHLC values, volume, metadata, and incomplete daily bars.

## Not Implemented

- Market-data downloading.
- Investment recommendations.
- Feature engineering or label generation.
- Machine-learning model training.
- Strategy generation.
- Backtesting.
- Risk calculations.
- Paper-order submission.
- Broker communication.
- Live trading.
- FastAPI endpoints.
- Streamlit pages.
- Database tables or persistence.

## Verification

Run tests:

```bash
pytest
```

Run linting:

```bash
ruff check .
```

Run format checks:

```bash
ruff format --check .
```

Run type checks:

```bash
mypy src tests
```

Run a package import check:

```bash
python -c "import spy_market_agent; print(spy_market_agent.__version__)"
```

## Documentation

- See `PROJECT_SPEC.md` for the approved architecture, safety requirements, phased plan, and known limitations.
- See `AGENTS.md` for permanent instructions future Codex tasks must follow.

No market-data downloading, feature engineering, model training, backtesting, risk calculations, API endpoints, dashboard functionality, database tables, paper-order submission, live trading, or broker integration is implemented in this phase.
