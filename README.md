# Risk-Controlled SPY Market Intelligence and Paper-Trading System

This project is a Python research scaffold for studying SPY market signals, evaluating future machine-learning baselines, running future historical backtests, and eventually preparing paper-only order submission behind independent risk controls.

The project is educational and experimental. It is not investment advice, and it must never claim or guarantee profitability.

## Status

Current development status: Phase 8 explicitly invoked paper-trading preparation. The project has local SQLite persistence, a read-only FastAPI presentation API, a read-only Streamlit dashboard, and an isolated Alpaca paper-only adapter behind durable safety controls.

The repository currently contains typed configuration, paper-only configuration validation, a provider-independent daily SPY schema, an XNYS calendar adapter, deterministic dataset checksums, data-quality validation, deterministic trailing feature engineering, forward open-to-open net-positive labels, supervised feature/label alignment, leakage-safe chronological train/validation/test splits, deterministic logistic-regression and gradient-boosting candidate training, validation-only model selection, locked train+validation refit, explicit final test evaluation, fixed long-or-cash test signals, independent long-only risk decisions, in-memory next-open backtesting, SQLite persistence for validated completed artifacts and local paper-execution audit records, a read-only FastAPI API, a read-only Streamlit dashboard, isolated broker-independent paper-execution interfaces, an Alpaca paper-only adapter, and tests. Market downloading, investment recommendations, automatic execution, API write routes, dashboard execution controls, scheduling, deployment, and live trading are not implemented.

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
- SQLite persistence for completed validated research artifacts.
- Read-only FastAPI backend for persisted results.
- Read-only Streamlit dashboard that consumes the FastAPI API.
- Explicitly invoked Alpaca paper trading preparation for SPY whole-share market DAY orders only.

## Safety Restrictions

- Live-money trading is not supported.
- `EXECUTION_MODE` may only be `paper`.
- Any request for live execution must raise `RuntimeError` in future configuration code.
- `ENABLE_PAPER_EXECUTION` defaults to `false`.
- `DRY_RUN` defaults to `true`.
- Application startup must not submit paper orders.
- The package import does not load settings or perform external actions.
- Models must never communicate directly with brokers.
- Paper-order submission is available only through explicit service calls with matching human approval, disengaged configuration and durable kill switches, duplicate protection, broker preflights, and execution-time risk approval.
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
src/spy_market_agent/persistence/  Explicit SQLite schema, serialization, and artifact repositories
src/spy_market_agent/execution/    Broker-independent paper execution models, ledger, service, and Alpaca paper adapter
src/spy_market_agent/api/          Read-only FastAPI application factory and response service
src/spy_market_agent/dashboard/    Streamlit dashboard and typed HTTP API client
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

The runtime dependencies include plain `uvicorn>=0.30,<1` for the documented local FastAPI startup command and `alpaca-py>=0.43.5,<0.44` for the isolated explicit Alpaca paper adapter.

Do not commit a real `.env` file. `.env.example` contains safe defaults and commented Alpaca paper credential placeholders only. The committed defaults cannot submit an order.

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

## Implemented Phase 7 Capabilities

- Versioned SQLite schema: `spy-sqlite-persistence-v1`.
- Explicit idempotent database initialization through `initialize_database(...)`; imports, API startup, and dashboard startup do not create or migrate database files.
- Persistence for validated `MarketDataBatch`, `FinalTestEvaluation`, and complete `BacktestResult` artifacts.
- Load paths reconstruct existing validated domain objects and rerun existing validation, checksum, risk, execution-price, accounting, and metric checks.
- Canonical serialization for dates, UTC datetimes, exact decimals, booleans, deterministic JSON, schema versions, SPY symbols, and SHA-256 checksums.
- Structured project-owned persistence errors for malformed input, conflicts, schema issues, integrity failures, and missing records.
- Read-only FastAPI application factory with typed Pydantic responses and bounded pagination.
- Streamlit dashboard views for overview, data quality, model evaluation, backtest results, and risk/audit.
- API and dashboard run IDs use the shared URL-safe contract `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`.
- Dashboard predictions, orders, risk decisions, and fills are bounded previews with visible `Showing X of Y` labels from API pagination metadata.
- Dashboard equity and drawdown charts fetch all equity pages from the API before plotting and fail visibly if pagination is inconsistent or chart values are non-finite.
- Dashboard data access goes through the FastAPI HTTP client only; it does not query SQLite directly.
- Educational warnings are shown in API responses and dashboard views. Results are not investment advice and do not prove profitability.

## Implemented Phase 8 Capabilities

- Versioned paper execution schema: `spy-paper-execution-v1`.
- Versioned SQLite persistence schema: `spy-sqlite-persistence-v2`, with explicit migration from the Phase 7 v1 schema and an engaged kill switch by default.
- Broker-independent immutable paper-execution models for instructions, approvals, broker snapshots, receipts, attempts, events, and local status.
- Shared URL-safe identifier contract for signal IDs, client-order IDs, and approval IDs: `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`.
- Deterministic SHA-256 instruction fingerprints over versioned order, risk, cost, session, timestamp, and identifier data.
- Human approval must match the exact instruction fingerprint and cannot be reused through the durable ledger.
- Durable duplicate protection for `signal_id`, `client_order_id`, and `approval_id`.
- Version 1 also permits at most one reserved SPY paper-execution attempt per execution session. The SQLite ledger enforces this on `(symbol, execution_session)` even when different signal, client-order, and approval IDs are supplied.
- A blocked, rejected, accepted, uncertain, broker-existing, or reconciled attempt still consumes that SPY execution session. This deliberately strict behavior prevents concurrent pyramiding and conflicting same-session submissions.
- Later execution sessions remain independently eligible after all normal configuration, approval, broker, risk, kill-switch, and duplicate checks pass.
- Configuration and durable global paper-execution kill switches both default to engaged. The effective kill-switch state is their logical OR, so both must be deliberately disengaged before an explicitly invoked paper submission can proceed.
- Durable kill-switch disengagement requires an explicit confirmation token and nonblank reason; changing configuration does not alter the durable SQLite switch.
- Explicit service-only submission path that rechecks configuration, credentials, kill switch, approval, staleness, broker state, open orders, positions, and execution-time risk before a broker call.
- Phase 8 always requires regular market hours; `PAPER_EXECUTION_REQUIRE_MARKET_OPEN` is retained for display compatibility but cannot be set to `false`.
- The broker clock is refreshed after reservation and broker lookup confirms no existing order. The fresh clock must still be open, timezone-aware, on the instruction execution session, before the exclusive expiration instant, and compatible with the approval.
- The durable kill switch is reread after the refreshed clock as the final persistent safety operation before submission. If it engages at that point, the reserved IDs remain blocked and no order is submitted.
- Engaging the kill switch after the final pre-submit check cannot cancel a broker request that is already in flight; order cancellation remains outside Phase 8.
- Alpaca adapter is paper-only, constructs `TradingClient(..., paper=True)` only when explicitly instantiated, and uses the canonical paper endpoint identity `https://paper-api.alpaca.markets`.
- Real Alpaca SDK enum values are normalized through their underlying values before broker preflight validation; malformed enum-like values fail closed.
- Supported order contract is SPY only, buy/sell only, whole shares only, market order, DAY time in force, `extended_hours=False`, and explicit `client_order_id`.
- Local order-request construction failures are blocked before submission and are not treated as uncertain broker outcomes. Once IDs are durably reserved, those IDs remain unavailable and cannot be silently reused.
- An instruction is invalid at its `expires_at_utc` instant; execution exactly at expiration is rejected before submission.
- Timeout, cancellation, connection loss, malformed post-submit responses, contradictory post-submit responses, or a local ledger failure after broker acceptance record `submission_unknown`, do not retry automatically, and require explicit read-only reconciliation by `client_order_id`.
- Same-session duplicate reservations and unknown submissions are never retried automatically.
- Only failures after the SDK submission may have started require reconciliation; local request-build failures do not.
- Broker lookup returns broker-observable order snapshots only. Reconciliation is lookup-only and binds those fields to persisted local signal IDs and instruction fingerprints; local lineage is never derived from broker order IDs or client-order IDs.
- The durable ledger independently enforces state transitions, persists event lineage from stored attempt rows, and rejects any receipt environment other than `alpaca_paper`.
- Read-only API routes expose local paper-trading status and local paper-order attempt history without constructing an Alpaca client.
- Dashboard adds a read-only Paper Trading Status view that consumes only the FastAPI API and contains no execution controls.

## Local Persistence, API, and Dashboard

Initialize or migrate a local SQLite database explicitly:

```bash
python -c "from spy_market_agent.persistence import initialize_database; initialize_database('./spy_market_agent.sqlite3')"
```

Start the read-only API after a database has been initialized and populated by approved research code:

```bash
python -m uvicorn "spy_market_agent.api.main:create_app" --factory --host 127.0.0.1 --port 8000
```

Available read-only routes:

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

Route `{run_id}` values must be 1 to 128 characters, start with an ASCII letter or digit, and contain only ASCII letters, digits, period, underscore, and hyphen. Values with whitespace, slashes, percent characters, query/fragment separators, colons, or other path-unsafe characters are rejected rather than normalized.

The paper-trading API routes are read-only local status views. They never create an Alpaca client, contact Alpaca, submit orders, change the kill switch, approve orders, or mutate broker state. Credential state is shown only as Boolean presence.

Start the Streamlit dashboard:

```bash
streamlit run src/spy_market_agent/dashboard/streamlit_app.py
```

Configure the dashboard API URL with `DASHBOARD_API_BASE_URL`; it defaults to `http://127.0.0.1:8000`. Configure the SQLite path with `SQLITE_DATABASE_PATH`; database directories are created only by explicit initialization.

Dashboard tables for predictions, orders, risk decisions, and fills are previews when the API total exceeds the visible rows. Equity and drawdown charts are intended to be complete; the dashboard retrieves all equity pages using the maximum API page size and shows an error instead of silently plotting partial or malformed chart data.

The Paper Trading Status dashboard tab is also read-only. It shows educational warnings, execution mode, paper-execution permission, dry-run state, configuration, durable, and effective kill-switch states, credential presence as booleans, unresolved submission count, and recent local paper-order attempts with visible pagination labels. It has no approve, submit, retry, reconcile, enable, disable, cancel, replace, or liquidation controls.

Paper market orders submitted after the market opens can fill differently from the Phase 6 next-open historical backtest assumption and do not represent real-money performance.

## Not Implemented

- Market-data downloading.
- Investment recommendations.
- Probability calibration.
- Threshold optimization.
- Trading-threshold optimization.
- Model binary persistence.
- API write routes.
- Dashboard write controls.
- Automatic broker communication.
- Automatic paper-order submission.
- API or dashboard execution controls.
- Order cancellation or replacement.
- Live trading.
- Schedulers or background workers.
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

No market-data downloading, probability calibration, threshold optimization, hyperparameter tuning, recommendations, model binary persistence, API write endpoint, dashboard write control, automatic execution, live trading, scheduling, or deployment functionality is implemented in this phase.
