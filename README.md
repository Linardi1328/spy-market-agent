# Risk-Controlled SPY Market Intelligence and Paper-Trading System

This project is a Python research scaffold for studying SPY market signals, evaluating future machine-learning baselines, running future historical backtests, and eventually preparing paper-only order submission behind independent risk controls.

The project is educational and experimental. It is not investment advice, and it must never claim or guarantee profitability.

## Status

Current development status: Phase 6 deterministic in-memory long-or-cash strategy signals, independent risk controls, and next-open backtesting.

The repository currently contains typed configuration, paper-only configuration validation, a provider-independent daily SPY schema, an XNYS calendar adapter, deterministic dataset checksums, data-quality validation, deterministic trailing feature engineering, forward open-to-open net-positive labels, supervised feature/label alignment, leakage-safe chronological train/validation/test splits, deterministic logistic-regression and gradient-boosting candidate training, validation-only model selection, locked train+validation refit, explicit final test evaluation, fixed long-or-cash test signals, independent long-only risk decisions, in-memory next-open backtesting, and tests. Market downloading, investment recommendations, order submission, broker communication, persistence, APIs, and dashboards are not implemented.

## Version 1 Scope

- Python 3.12.
- SPY ETF only.
- Daily OHLCV market-data validation.
- Long-or-cash positions only.
- No short selling.
- No leverage.
- In-memory historical research backtesting.
- Initial simulated capital of USD 10,000.
- Logistic regression baseline and gradient boosting comparison.
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
src/spy_market_agent/features/     Leakage-safe trailing feature engineering
src/spy_market_agent/datasets/     Forward labels, supervised datasets, and chronological splits
src/spy_market_agent/modeling/     Deterministic model training, validation selection, and test evaluation
src/spy_market_agent/strategies/   Fixed long-or-cash signal policy
src/spy_market_agent/risk/         Independent SPY-only long-only risk controls
src/spy_market_agent/backtesting/  In-memory next-open backtest accounting and metrics
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

## Implemented Phase 4 Capabilities

- Versioned ordered daily SPY feature schema: `spy-daily-features-v1`.
- Deterministic trailing features using only completed sessions through `t`.
- Warm-up exclusion for the first 20 source rows, with fail-closed validation for non-finite post-warm-up values.
- Versioned forward label schema: `spy-open-t1-to-open-t6-net-positive-v1`.
- Explicit immutable cost assumptions for commission and slippage in basis points per side.
- Label timeline: feature information through session `t`, entry at the open of `t + 1`, exit at the open of `t + 6`, and target `1` only when net return after costs is strictly positive.
- Supervised dataset assembly that keeps feature columns separate from label audit columns.
- `X` and `y` accessors that return ordered numerical features only and binary targets only.
- Chronological train, validation, and test split specifications using explicit session-date boundaries.
- Leakage-safe split assignment requiring each row's `exit_session` to remain inside the partition boundary.
- Tests proving future rows cannot affect past features, labels use trading-session row offsets, and boundary-crossing labels are purged.

## Implemented Phase 5 Capabilities

- Versioned modeling schema: `spy-binary-models-v1`.
- Frozen `ModelTrainingConfig` with deterministic random seed and diagnostic classification threshold.
- Fixed logistic-regression baseline using a scikit-learn `Pipeline` with `StandardScaler` fitted on train features only.
- Fixed `GradientBoostingClassifier` comparison model with no scaling, tuning, early stopping, class weighting, resampling, or synthetic observations.
- Candidate comparison that accepts only train and validation partitions; the test partition is not part of the candidate-training API.
- Validation-only model-selection rule: higher ROC AUC, then lower log loss, then lower Brier score, then logistic regression as the final tie-break.
- Locked selected model refit on train plus validation only, using a fresh estimator.
- Separate final test evaluation that never changes the selected model, parameters, preprocessing, threshold, or selection rationale.
- Prediction audit frames for diagnostics only, with `session`, `probability_positive`, `predicted_class`, and `target`.
- Classification metrics for train, validation, and final test diagnostics. These are not trading-performance metrics and are not evidence of profitability.
- Structured Phase 5 errors for expected malformed inputs, training failures, evaluation failures, selection failures, and locked-model failures.

## Implemented Phase 6 Capabilities

- Versioned fixed long-or-cash strategy schema: `spy-long-cash-strategy-v1`.
- Strategy target positions derived from locked final-test `probability_positive` only, using the fixed `0.5` Phase 6 threshold.
- Next-open execution mapping from signal session `t` to the immediate next validated market-data row, not calendar-day arithmetic.
- Explicit immutable backtest cost assumptions for commission and slippage in basis points per side.
- Independent SPY-only long-only risk configuration that rejects short selling, leverage, fractional shares, and non-SPY symbols.
- Proposed orders, risk decisions, fills, portfolio/equity rows, and metrics as deterministic in-memory audit DataFrames.
- Backtest accounting for cash, whole shares, market value, equity, daily return, drawdown, turnover, exposure, transaction costs, and rejected orders.
- Rejected orders never create fills or alter portfolio state; every fill references an approved risk decision.
- No model refit, probability generation, broker communication, persistence, API, dashboard, paper order, or live order behavior occurs in Phase 6.

## Not Implemented

- Market-data downloading.
- Investment recommendations.
- Probability calibration.
- Threshold optimization.
- Trading-threshold optimization.
- Model persistence.
- Database persistence.
- SQLite persistence.
- APIs.
- Dashboards.
- Broker communication.
- Alpaca integration.
- Paper-order submission.
- Live trading.
- Deployment.

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

No market-data downloading, probability calibration, threshold optimization, hyperparameter tuning, recommendations, model persistence, database persistence, SQLite persistence, API endpoint, dashboard functionality, broker communication, Alpaca integration, paper-order submission, live trading, or deployment functionality is implemented in this phase.
