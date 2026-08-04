# Workflows

These workflows are safe local operations. They do not submit broker orders.

## Run Verification

```bash
python -m pip install -e ".[dev]"
pytest --cov-fail-under=85
pytest tests/unit -q
pytest tests/integration -q
ruff check .
ruff format --check .
mypy src tests
```

## Initialize SQLite Explicitly

```bash
python -c "from spy_market_agent.persistence import initialize_database; initialize_database('./spy_market_agent.sqlite3')"
```

This creates or migrates only the named local SQLite file. It does not download data, run a
backtest, create a broker client, or submit an order.

## Start the Read-Only FastAPI Application

```bash
python -m uvicorn "spy_market_agent.api.main:create_app" --factory --host 127.0.0.1 --port 8000
```

The app reads from `./spy_market_agent.sqlite3` by default. Empty or unavailable databases
return read-safe empty responses or sanitized service errors.

## Start the Streamlit Dashboard

```bash
streamlit run src/spy_market_agent/dashboard/streamlit_app.py
```

The dashboard reads from the FastAPI API configured by `DASHBOARD_API_BASE_URL`, which
defaults to `http://127.0.0.1:8000`.

## Load Deterministic Test or Demo Data

Version 1 has no committed real SPY dataset. Version 2 Phase 1 adds an explicit historical
SPY acquisition path that is under review and stores downloaded provider data only in ignored
local directories. The existing supported deterministic data paths are automated tests that
create synthetic artifacts in temporary directories:

```bash
pytest tests/unit/test_v2_phase1_market_data.py -q
pytest tests/integration/test_v2_phase1_acquisition_flow.py -q
pytest tests/integration/test_phase7_persistence_api_dashboard_flow.py -q
pytest tests/integration/test_phase8_paper_execution_flow.py -q
```

For a manual demo database, use the public repository APIs from your own local script with
validated `MarketDataBatch`, `FinalTestEvaluation`, and `BacktestResult` objects. Do not commit
the generated SQLite file or any external market data.

## Acquire Historical SPY Daily Data Explicitly

This command contacts the Alpaca Market Data API only when invoked directly. It does not
initialize SQLite, train a model, run a backtest, contact the trading API, or submit an
order.

```bash
ALPACA_MARKET_DATA_API_KEY=... \
ALPACA_MARKET_DATA_SECRET_KEY=... \
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

The dates above are a small example only. Alpaca account access, feed selection, subscription
level, and provider history determine what data is actually available. Do not commit
downloaded provider data. `MARKET_DATA_TIMEOUT_SECONDS` bounds each provider HTTP request;
`MARKET_DATA_MAX_RETRIES` controls retry count separately.

## Verify a Local Phase 1 Dataset

```bash
python -m spy_market_agent.market_data.cli verify \
  --manifest data/manifests/alpaca/SPY/1Day/sip/all/DATASET_ID.manifest.json \
  --data-root ./data
```

This performs deep offline verification. It validates the manifest model and self-checksum,
verifies raw and canonical artifact hashes, parses the sanitized raw JSON and canonical CSV,
recomputes source and canonical content checksums, recomputes the dataset ID, checks generated
file paths and filenames, confirms row counts and session ranges, and reruns OHLCV and XNYS
session validation from recorded acquisition metadata. It performs no network request.

Acquisition writes raw, canonical, and manifest files as a multi-artifact operation. If a
later write fails, files newly created by that attempt are cleaned up best-effort; matching
files that existed before the attempt are preserved.

## Inspect Model Evaluations

With the read API running:

```bash
curl http://127.0.0.1:8000/api/v1/model-runs
curl http://127.0.0.1:8000/api/v1/model-runs/RUN_ID
curl "http://127.0.0.1:8000/api/v1/model-runs/RUN_ID/predictions?limit=100&offset=0"
```

Replace `RUN_ID` with a persisted run ID. Classification metrics are diagnostics only and do
not establish profitability.

## Inspect Backtest Results

```bash
curl http://127.0.0.1:8000/api/v1/backtests
curl http://127.0.0.1:8000/api/v1/backtests/RUN_ID
curl "http://127.0.0.1:8000/api/v1/backtests/RUN_ID/equity?limit=100&offset=0"
curl "http://127.0.0.1:8000/api/v1/backtests/RUN_ID/orders?limit=100&offset=0"
curl "http://127.0.0.1:8000/api/v1/backtests/RUN_ID/risk-decisions?limit=100&offset=0"
curl "http://127.0.0.1:8000/api/v1/backtests/RUN_ID/fills?limit=100&offset=0"
```

Historical backtests are approximations and do not guarantee future or executable results.

## Inspect Local Paper-Execution Status

```bash
curl http://127.0.0.1:8000/api/v1/paper-trading/status
curl "http://127.0.0.1:8000/api/v1/paper-orders?limit=100&offset=0"
curl http://127.0.0.1:8000/api/v1/paper-orders/CLIENT_ORDER_ID
```

These routes inspect local SQLite audit state only. They do not construct an Alpaca client,
change kill switches, approve orders, reconcile orders, or submit orders.

## Paper-Order Instruction and Approval Concept

The executable submission path is intentionally omitted from copyable shell commands. A
paper submission requires this conceptual sequence:

```text
PSEUDOCODE ONLY - do not paste

1. Build a ProposedOrder from an approved strategy and backtest/risk workflow.
2. Run independent risk evaluation and require an approved RiskDecision.
3. Build a PaperOrderInstruction with unique signal_id and client_order_id.
4. Review the deterministic instruction_fingerprint.
5. Record human approval with a unique approval_id bound to that exact fingerprint.
6. Confirm paper mode, paper execution enabled, dry-run disabled, configuration kill switch off.
7. Confirm the durable SQLite kill switch has been explicitly disengaged.
8. Confirm broker preflights, market hours, SPY asset, positions, open orders, and risk pass.
9. Reserve IDs and the SPY execution session before any broker submission.
10. Submit only through the explicit service call if every gate passes.
```

Any timeout or uncertain post-submit result must be treated as `submission_unknown`. Do not
resubmit automatically; use lookup-only reconciliation by `client_order_id`.
