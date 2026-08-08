# Risk-Controlled SPY Market Intelligence and Paper-Trading System

`spy-market-agent` is an educational Python 3.12 project for researching SPY daily
signals, evaluating leakage-aware machine-learning baselines, running risk-controlled
long-or-cash backtests, persisting audit artifacts in SQLite, and preparing explicitly
approved Alpaca paper orders behind fail-closed safety gates.

It is experimental research software. It is not investment advice, does not claim
profitability, and is not real-money trading infrastructure.

## Release Status

- Current stable historical baseline: `v1.0.0`.
- Current package/runtime version: `2.0.0a2`.
- Current released identifier remains `v2.0.0-alpha.1` until the reviewed release-preparation
  branch is merged and tagged.
- Release-preparation target: `v2.0.0-alpha.2`.
- V2 Phase 1: accepted and complete - Real SPY Data Foundation.
- V2 Phase 2: engineering acceptance complete - Real Historical Benchmark.
- Owner-run real SIP benchmark and one controlled final-test execution completed.
- No Phase 3 implementation has begun.
- Live-money readiness: not approved.

Version 2 Phase 1 uses package version `2.0.0a1` and release identifier
`v2.0.0-alpha.1`. Version 2 Phase 2 prepares package version `2.0.0a2` for release
identifier `v2.0.0-alpha.2`. Release tags must point only to successfully verified `main`
commits after review approval and merge.

## Version 1 Historical Baseline

Version 1.0.0 covers the completed Phase 1 through Phase 8 implementation plus the Phase 9
documentation and release-readiness work. It remains the frozen historical baseline:

- SPY ETF only.
- Daily OHLCV data only.
- Long-or-cash positions only.
- No short selling, leverage, margin, fractional-share orders, or additional markets.
- Provider-independent market-data contracts and validation, but no market-data downloader
  in Version 1.0.0.
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

## Version 2 Phase 1 Alpha

Version 2 Phase 1 adds an accepted historical SPY daily-data foundation. It uses package
version `2.0.0a1` and release identifier `v2.0.0-alpha.1`. The release tag must point only
to a successfully verified `main` commit.

Phase 1 provides:

- Explicit user-triggered SPY historical-data acquisition.
- An Alpaca Market Data API provider adapter.
- Separate market-data credentials.
- Sanitized raw JSON snapshots.
- Canonical validated CSV bars.
- Deterministic manifests, SHA-256 checksums, and dataset identity.
- XNYS session validation and OHLCV validation.
- Deep offline dataset verification.
- Safe local ignored provider-data storage under `data/raw/`, `data/canonical/`, and
  `data/manifests/`.

Example explicit acquisition command:

```bash
python -m spy_market_agent.market_data.cli acquire \
  --provider alpaca \
  --symbol SPY \
  --start 2016-01-04 \
  --end 2016-01-08 \
  --timeframe 1Day \
  --feed sip \
  --adjustment all \
  --data-root ./data \
  --acknowledge-provider-terms
```

Credentials are optional for normal tests. Real Alpaca market-data acquisition requires
`ALPACA_MARKET_DATA_API_KEY` and `ALPACA_MARKET_DATA_SECRET_KEY`; these are separate from
paper-trading credentials and are read only from the environment. Downloaded provider data is
local and ignored under `data/raw/`, `data/canonical/`, and `data/manifests/`.

Phase 1 does not train models, run benchmarks, test prediction accuracy, claim profitability,
submit orders, add real-time operation, or enable live trading.

## Version 2 Phase 2 Alpha Candidate

Version 2 Phase 2 adds accepted real historical benchmark infrastructure and owner-run
acceptance evidence for the existing approved SPY research workflow. It uses a verified
Alpaca SIP, `1Day`, adjustment `all` SPY dataset from 2018-01-02 through 2025-12-31. The
owner-run benchmark used dataset ID `spy-v2p1-825930b0a2bcab20c733b867` and benchmark ID
`spy-v2p2-a065593e952e6a9d96f4be86`; generated provider data and benchmark artifacts remain
ignored and are not distributed with the repository.

Engineering result:

- Implementation PR #20 was merged at main commit `1155c3c`.
- Dataset verification, benchmark verification, and runtime-lineage verification passed in
  the owner environment.
- Validation, final-test locking, one controlled final-test execution, completion evidence,
  and audit verification completed.
- Owner-run quality gates passed: 999 tests, 85% coverage, Ruff, formatting, MyPy, and clean
  working tree.

Scientific result:

- `logistic_regression` was selected over `gradient_boosting` by higher validation ROC AUC.
- Final-test ROC AUC was `0.4640772128060263`, below `0.5`.
- Final-test log loss and Brier score did not beat the training-prevalence baseline.
- The selected model predicted positive on about `97.6%` of final-test rows, behaving close
  to an almost-always-long signal during that period.

This is valid benchmark evidence and not an engineering failure. It does not establish a
reliable predictive edge, trading readiness, profitability, or investment suitability.

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

The current implemented system intentionally does not include:

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

Version 2 Phase 2 includes completed historical benchmarking on one owner-run real SPY SIP
dataset. It does not include model research beyond the approved locked candidates and does
not prove predictive market edge.

Version 1.0.0 specifically did not include market-data downloading; the explicit SPY
historical-data acquisition CLI begins in Version 2 Phase 1.

## Quick Start — Open the Local Dashboard

This workflow launches the application locally in your browser. It is not a public internet
deployment. No Alpaca credentials are required for the safe dashboard demo. The API and
dashboard are read-only, no order is submitted, and an empty dashboard is expected until
research artifacts are persisted.

### 1. Clone and Enter the Repository

```bash
git clone https://github.com/Linardi1328/spy-market-agent.git
cd spy-market-agent

pwd
git rev-parse --show-toplevel
test -f pyproject.toml && echo "Repository root confirmed"
```

Editable installation fails with errors such as `neither setup.py nor pyproject.toml found`
when these commands are run from your home directory or another folder.

### 2. Create and Activate a Python 3.12 Environment

macOS/Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

python --version
python -c "import spy_market_agent; print(spy_market_agent.__version__)"
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

python --version
python -c "import spy_market_agent; print(spy_market_agent.__version__)"
```

The import command is the source of truth for the package version on your branch.

### 3. Initialize the Local Database Explicitly

```bash
python -c "from spy_market_agent.persistence import initialize_database; initialize_database('./spy_market_agent.sqlite3')"
test -f spy_market_agent.sqlite3 && echo "Database initialized"
```

Initialization does not download data, train a model, contact Alpaca, or submit an order.
The database file is local and ignored by Git.

### 4. Start FastAPI in Terminal A

Open a new terminal window or tab. Keep this command running. Do not type the Streamlit
command into the same active terminal.

```bash
cd /path/to/spy-market-agent
source .venv/bin/activate

SQLITE_DATABASE_PATH=./spy_market_agent.sqlite3 \
python -m uvicorn "spy_market_agent.api.main:create_app" \
  --factory \
  --host 127.0.0.1 \
  --port 8000
```

PowerShell:

```powershell
cd C:\path\to\spy-market-agent
.venv\Scripts\Activate.ps1

$env:SQLITE_DATABASE_PATH="./spy_market_agent.sqlite3"
python -m uvicorn "spy_market_agent.api.main:create_app" `
  --factory `
  --host 127.0.0.1 `
  --port 8000
```

The FastAPI terminal must remain open.

### 5. Verify FastAPI Before Starting Streamlit

In another terminal, run:

```bash
curl http://127.0.0.1:8000/health
```

The response should contain `"status":"ok"`. You can also open
`http://127.0.0.1:8000/health` in a browser. Do not continue until the health check works.

### 6. Start Streamlit in Terminal B

Use another terminal window or tab; this is a separate terminal from Terminal A:

```bash
cd /path/to/spy-market-agent
source .venv/bin/activate

DASHBOARD_API_BASE_URL=http://127.0.0.1:8000 \
streamlit run src/spy_market_agent/dashboard/streamlit_app.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false
```

PowerShell:

```powershell
cd C:\path\to\spy-market-agent
.venv\Scripts\Activate.ps1

$env:DASHBOARD_API_BASE_URL="http://127.0.0.1:8000"
streamlit run src/spy_market_agent/dashboard/streamlit_app.py `
  --server.address 127.0.0.1 `
  --server.port 8501 `
  --server.headless true `
  --browser.gatherUsageStats false
```

Headless mode avoids Streamlit's first-run email prompt.

### 7. Open the Application

- Dashboard: `http://127.0.0.1:8501`
- API health: `http://127.0.0.1:8000/health`
- FastAPI interactive documentation: `http://127.0.0.1:8000/docs`

These addresses work only while their corresponding terminal processes remain running.

### 8. Expected First-Run Behavior

A newly initialized database may correctly show no persisted market-data status, no model
runs, no backtests, no paper-order attempts, paper execution disabled, dry-run enabled, kill
switches engaged, and Alpaca credential presence false.

This proves the interface and API are running. It does not prove that a model benchmark has
been executed.

### 9. Stop and Clean Up

Stop each server with `Ctrl+C` in its own terminal. Optional cleanup:

```bash
deactivate 2>/dev/null || true
rm -rf .venv
rm -f spy_market_agent.sqlite3
git status --short
```

Do not delete ignored Phase 1 market-data files or benchmark artifacts unless you
intentionally created them and no longer need them.

### 10. Troubleshooting

Error: `neither setup.py nor pyproject.toml found`

Cause: the command was run outside the repository root.

Fix:

```bash
cd spy-market-agent
test -f pyproject.toml && echo "Repository root confirmed"
```

Error: `ModuleNotFoundError: spy_market_agent`

Fix:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Error: dashboard says API unavailable

Fix: confirm the FastAPI terminal is still running, open
`http://127.0.0.1:8000/health`, confirm `DASHBOARD_API_BASE_URL`, and confirm ports `8000`
and `8501` are not occupied.

Error: database unavailable

Fix: initialize `spy_market_agent.sqlite3` and ensure `SQLITE_DATABASE_PATH` points to the
same file used during initialization.

Error: port already in use

Fix: stop the process using the port or choose local alternatives, for example FastAPI
`--port 8001` and Streamlit `--server.port 8502`. If FastAPI uses a different port, set
`DASHBOARD_API_BASE_URL` to match it.

Error: dashboard opens but contains no results

Fix: the database is empty. Research artifacts must be generated and persisted through
approved workflows before model runs or backtests appear.

Detailed guides use the same local database, ports, and startup order:
[Demo Guide](docs/DEMO_GUIDE.md), [Workflows](docs/WORKFLOWS.md),
[Reproducibility](docs/REPRODUCIBILITY.md), and
[Security and Safety](docs/SECURITY_AND_SAFETY.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Reproducibility](docs/REPRODUCIBILITY.md)
- [Workflows](docs/WORKFLOWS.md)
- [Security and Safety](docs/SECURITY_AND_SAFETY.md)
- [Demo Guide](docs/DEMO_GUIDE.md)
- [Portfolio Overview](docs/PORTFOLIO_OVERVIEW.md)
- [Future Roadmap](FUTURE_ROADMAP.md)
- [Version 2 Phase 1 Real SPY Data Specification](docs/V2_PHASE_01_REAL_SPY_DATA_SPEC.md)
- [Version 2 Phase 1 Provider Decision](docs/V2_PHASE_01_PROVIDER_DECISION.md)
- [Version 2 Phase 2 Real Historical Benchmark Specification](docs/V2_PHASE_02_REAL_HISTORICAL_BENCHMARK_SPEC.md)
- [Version 2 Phase 2 Benchmark Policy](docs/V2_PHASE_02_BENCHMARK_POLICY.md)
- [Version 2 Phase 2 Data Card Template](docs/V2_PHASE_02_DATA_CARD_TEMPLATE.md)
- [Version 2.0.0 Alpha 1 Release Notes](RELEASE_NOTES_V2.0.0_ALPHA_1.md)
- [Version 2.0.0 Alpha 2 Release Notes](RELEASE_NOTES_V2.0.0_ALPHA_2.md)
- [Version 2 Phase 1 Release Checklist](VERSION_2_PHASE_01_RELEASE_CHECKLIST.md)
- [Version 2 Phase 2 Release Checklist](VERSION_2_PHASE_02_RELEASE_CHECKLIST.md)
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
