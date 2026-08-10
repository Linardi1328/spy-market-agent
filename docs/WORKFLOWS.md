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
test -f spy_market_agent.sqlite3 && echo "Database initialized"
```

This creates or migrates only the named local SQLite file. It does not download data, run a
backtest, create a broker client, or submit an order.

## Start the Read-Only FastAPI Application

```bash
SQLITE_DATABASE_PATH=./spy_market_agent.sqlite3 \
python -m uvicorn "spy_market_agent.api.main:create_app" \
  --factory \
  --host 127.0.0.1 \
  --port 8000
```

Keep this terminal open. The app reads from `./spy_market_agent.sqlite3`. Empty or
unavailable databases return read-safe empty responses or sanitized service errors.

Verify before starting Streamlit:

```bash
curl http://127.0.0.1:8000/health
```

## Start the Streamlit Dashboard

```bash
DASHBOARD_API_BASE_URL=http://127.0.0.1:8000 \
streamlit run src/spy_market_agent/dashboard/streamlit_app.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false
```

The dashboard reads from the FastAPI API configured by `DASHBOARD_API_BASE_URL`, which
points to `http://127.0.0.1:8000` in this workflow. Use a separate terminal from FastAPI.
Headless mode avoids Streamlit's first-run email prompt. Open
`http://127.0.0.1:8501` after the Streamlit endpoint responds.

## Load Deterministic Test or Demo Data

Version 1 has no committed real SPY dataset. Version 2 Phase 1 adds an accepted explicit
historical SPY acquisition path and stores downloaded provider data only in ignored local
directories. The existing supported deterministic data paths are automated tests that create
synthetic artifacts in temporary directories:

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

## Prepare a Phase 2 Benchmark Lock

Phase 2 benchmark commands are manually invoked, offline, and file-based. They do not contact
Alpaca, construct a broker client, initialize SQLite, submit orders, or run a real final test
without explicit final-test acknowledgement.

Record owner-provided feed evidence:

```bash
python -m spy_market_agent.benchmark.cli record-feed-decision \
  --provider alpaca \
  --feed sip \
  --symbol SPY \
  --timeframe 1Day \
  --adjustment all \
  --start 2016-01-04 \
  --end 2025-12-31 \
  --available \
  --owner-acknowledge \
  --evidence-source "owner offline probe summary" \
  --output artifacts/benchmarks/local-feed-decision.json
```

Prepare the immutable benchmark lock from a verified Phase 1 manifest:

```bash
python -m spy_market_agent.benchmark.cli prepare \
  --manifest data/manifests/alpaca/SPY/1Day/sip/all/DATASET_ID.manifest.json \
  --feed-record artifacts/benchmarks/local-feed-decision.json \
  --benchmark-role primary \
  --latest-complete-research-year 2025 \
  --artifact-root ./artifacts/benchmarks \
  --owner-approve-assumptions
```

Generated benchmark outputs remain ignored under `artifacts/benchmarks/<benchmark_id>/`.
Codex verification uses synthetic manifests only. The owner-run primary real SIP benchmark
for `v2.0.0-alpha.2` has completed; do not rerun or reopen that final test during Phase 3
research. Record only sanitized summary evidence in Git.

Deep-verify a benchmark directory offline:

```bash
python -m spy_market_agent.benchmark.cli verify \
  --benchmark-root artifacts/benchmarks/BENCHMARK_ID
```

Require current runtime lineage to match the frozen lock during verification:

```bash
python -m spy_market_agent.benchmark.cli verify \
  --benchmark-root artifacts/benchmarks/BENCHMARK_ID \
  --require-runtime-lineage
```

Run Stage A validation only after reviewing the lock and assumptions:

```bash
python -m spy_market_agent.benchmark.cli run-validation \
  --benchmark-lock artifacts/benchmarks/BENCHMARK_ID/benchmark_lock.json
```

Finalize the final-test lock only after validation review:

```bash
python -m spy_market_agent.benchmark.cli finalize-lock \
  --benchmark-lock artifacts/benchmarks/BENCHMARK_ID/benchmark_lock.json \
  --acknowledge-final-test-policy
```

Stage B final-test access is an owner-run controlled action and must not be run by Codex
during Phase 3 research. For the accepted Phase 2 benchmark, this command has already been
run once by the owner. A new non-audit run would require a new approved benchmark identity.
The command writes immutable `final_test_access.json` before loading final-test labels and
writes `final_test_completion.json` only after all final artifacts are completed:

```bash
python -m spy_market_agent.benchmark.cli run-final-test \
  --final-test-lock artifacts/benchmarks/BENCHMARK_ID/final_test_lock.json \
  --acknowledge-final-test-access
```

Audit replay verifies an existing completed final-test bundle without creating a new access
record or overwriting accepted artifacts:

```bash
python -m spy_market_agent.benchmark.cli run-final-test \
  --final-test-lock artifacts/benchmarks/BENCHMARK_ID/final_test_lock.json \
  --audit-replay
```

## Prepare Phase 3 Walk-Forward Research

Phase 3 is active for framework implementation and initial research scaffolding under
`docs/V2_PHASE_03_WALK_FORWARD_RESEARCH_SPEC.md`. It starts from the completed
`v2.0.0-alpha.2` benchmark evidence, but it must not tune against the already-opened Phase 2
final test.

The required planning workflow is:

1. Confirm the active branch is `review/v2-phase-03-walk-forward-research`.
2. Read `AGENTS.md`, `PROJECT_SPEC.md`, `FUTURE_ROADMAP.md`, and the Phase 3 specification.
3. Treat Phase 2 final-test row-level labels, predictions, strategy rows, fills, and
   generated benchmark JSON as unavailable for research.
4. Define walk-forward folds chronologically with the six-row boundary exclusion before any
   feature, model, calibration, threshold, or strategy research.
5. Record experiment lineage before substantive real-data research.
6. Keep generated research artifacts ignored under `artifacts/research/<experiment_id>/`.
7. Report classification metrics separately from strategy metrics.

The recommended default Phase 3 protocol is expanding-window walk-forward validation:

```text
minimum initial training rows: 756
boundary exclusion after training: 6 supervised rows
assessment window: 126 supervised rows
step size: 63 supervised rows
```

The current Phase 3 scaffolding is programmatic and package-local under
`src/spy_market_agent/research`; it can construct and validate fold, registry, manifest,
metric, baseline, calibration, threshold, and artifact records from offline inputs. No
Phase 3 research CLI command is currently exposed. Any future command must be manual,
offline for normal tests, credential-free, broker-free, and unable to submit paper or live
orders.

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
