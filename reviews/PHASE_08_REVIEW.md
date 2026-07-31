# Phase 8 Review: Paper-Trading Preparation

## Phase Objective

Implement a deliberately invoked, auditable, fail-closed paper-execution layer for SPY using Alpaca paper trading only.

Phase 8 adds broker-independent execution models, a durable SQLite execution ledger, a persistent kill switch, duplicate protection, explicit human approval binding, an Alpaca paper-only adapter, and read-only API/dashboard status views. It does not add live trading, automatic execution, API write routes, dashboard execution controls, schedulers, deployment, authentication, cancellation, replacement, liquidation, or Phase 9 behavior.

## Branch and Baseline

- Review branch: `review/phase-08-paper-trading-preparation`
- Starting main SHA: `d5e2a81ed51951b414100e440796397cb3cbd938`
- `origin/main` SHA at branch creation: `d5e2a81ed51951b414100e440796397cb3cbd938`
- Phase 8 final commit SHA: to be recorded in the final Codex response after commit creation.

## Dependency

- Added runtime dependency: `alpaca-py>=0.43.5,<0.44`
- Installed version during implementation: `0.43.5`
- The Alpaca SDK is imported only by `src/spy_market_agent/execution/alpaca_paper.py`.
- MyPy override is limited to `alpaca` and `alpaca.*`.

## Files Created

- `reviews/PHASE_08_REVIEW.md`
- `src/spy_market_agent/execution/alpaca_paper.py`
- `src/spy_market_agent/execution/approvals.py`
- `src/spy_market_agent/execution/errors.py`
- `src/spy_market_agent/execution/identifiers.py`
- `src/spy_market_agent/execution/models.py`
- `src/spy_market_agent/execution/protocols.py`
- `src/spy_market_agent/execution/repository.py`
- `src/spy_market_agent/execution/service.py`
- `tests/integration/test_phase8_paper_execution_flow.py`
- `tests/unit/phase8_helpers.py`
- `tests/unit/test_alpaca_paper_adapter.py`
- `tests/unit/test_api_phase8.py`
- `tests/unit/test_execution_models.py`
- `tests/unit/test_execution_repository.py`
- `tests/unit/test_execution_service.py`
- `tests/unit/test_execution_settings.py`

## Files Modified

- `.env.example`
- `PROJECT_SPEC.md`
- `README.md`
- `pyproject.toml`
- `src/spy_market_agent/api/__init__.py`
- `src/spy_market_agent/api/main.py`
- `src/spy_market_agent/api/schemas.py`
- `src/spy_market_agent/api/services.py`
- `src/spy_market_agent/config/__init__.py`
- `src/spy_market_agent/config/settings.py`
- `src/spy_market_agent/dashboard/app.py`
- `src/spy_market_agent/dashboard/client.py`
- `src/spy_market_agent/execution/__init__.py`
- `src/spy_market_agent/persistence/database.py`
- `src/spy_market_agent/persistence/schema.py`
- `tests/integration/test_phase7_persistence_api_dashboard_flow.py`
- `tests/unit/test_dashboard_phase7.py`
- `tests/unit/test_public_phase7_api.py`
- `tests/unit/test_settings.py`

## Execution Architecture

- Public execution interfaces live in `spy_market_agent.execution`.
- Domain models, protocols, service, approvals, identifiers, and repository code do not import Alpaca SDK classes.
- `PaperExecutionService` depends on `PaperBrokerProtocol`, not on `TradingClient`.
- `AlpacaPaperBroker` is isolated in `execution/alpaca_paper.py`.
- Modeling, strategy, and risk packages do not import Alpaca.
- Package import, API factory construction, API startup, dashboard import, and dashboard rendering do not construct a broker client.

## Schema and Migration

- Execution schema version: `spy-paper-execution-v1`
- SQLite persistence schema version: `spy-sqlite-persistence-v2`
- Phase 7 schema version retained for migration recognition: `spy-sqlite-persistence-v1`
- `initialize_database(...)` explicitly initializes or migrates the schema in one transaction.
- Fresh v2 initialization creates all Phase 7 tables, Phase 8 tables, and an engaged kill-switch singleton.
- v1-to-v2 migration is non-destructive and creates the kill switch engaged.
- Repeated initialization is idempotent.
- Unsupported future schema versions are rejected.
- API and dashboard startup do not initialize or migrate SQLite.

## Execution Ledger Tables

- `paper_execution_control`
- `paper_execution_attempts`
- `paper_execution_events`

The ledger uses unique constraints for `signal_id`, `client_order_id`, and `approval_id`. Events reference attempts by `client_order_id` when present and are append-only. No secrets, authorization headers, full account IDs, account numbers, environment variables, raw SDK payloads, or tracebacks are persisted.

## State Machine

Closed local attempt states:

- `reserved`
- `broker_existing_order_found`
- `accepted`
- `rejected`
- `submission_unknown`
- `reconciled`
- `blocked`

`submission_unknown` retains the reservation and prevents reuse of the signal, client-order, and approval IDs.

## Kill Switch

- The durable paper-execution kill switch defaults to engaged.
- Missing kill-switch state is interpreted as engaged.
- Corrupted kill-switch state raises `PaperExecutionIntegrityError`.
- Disengagement requires a nonblank reason and exact confirmation token `DISENGAGE_PAPER_EXECUTION_KILL_SWITCH`.
- Re-engagement is explicit and does not require broker credentials.
- State changes are timestamped and audited in `paper_execution_events`.
- No API route or dashboard control can change the kill switch.

## Identifier and Fingerprint Contracts

- Shared identifier pattern: `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`
- Applies to `signal_id`, `client_order_id`, and `approval_id`.
- No normalization or trimming is performed.
- Deterministic instruction fingerprints are SHA-256 hashes over canonical versioned JSON containing schema version, IDs, proposed order fields, original risk decision fields, cost assumptions, instruction timestamps, symbol, side, quantity, signal session, and execution session.

## Approval Contract

- `PaperOrderApproval.approved` must be exactly `True`.
- Approval must match `signal_id`, `client_order_id`, and instruction fingerprint.
- Approval must be strictly after instruction creation and not from the future at execution time.
- Approval expires with the instruction.
- Approval IDs are durable and non-reusable.

## Broker Protocol and Alpaca Mapping

`PaperBrokerProtocol` exposes only the preflight and submission operations needed by the service:

- environment verification
- account snapshot
- account configuration snapshot
- clock snapshot
- SPY asset lookup
- position list
- open-order list
- lookup by client-order ID
- submit market DAY order

The Alpaca adapter:

- Constructs `TradingClient(..., paper=True)` only when explicitly instantiated.
- Does not expose `paper` or base URL as caller-configurable options.
- Uses endpoint identity `https://paper-api.alpaca.markets`.
- Maps only SPY, buy/sell, whole-share quantity, market order, DAY time in force, `extended_hours=False`, and explicit `client_order_id`.
- Rejects malformed or contradictory broker responses.
- Does not automatically retry `submit_order`.

## Preflight Order

Every explicit submission checks:

- local configuration is paper, enabled, non-dry-run, and credential-present
- broker environment is paper and endpoint identity matches the canonical paper endpoint
- account is active, USD, unblocked, unsuspended, and has finite nonnegative balances
- account configuration has no shorting, margin multiplier 1, and no suspended trading
- broker clock is open and on the instruction execution session
- instruction is not expired or stale
- approval matches the exact instruction
- kill switch is disengaged immediately before submission
- SPY asset is active, tradable, and US equity
- positions are Version 1 compliant
- open orders are Version 1 compliant
- execution-time risk re-evaluation approves the order
- IDs are atomically reserved before broker submission
- broker lookup by `client_order_id` is performed before submission

## Restrictions

- No live endpoint support.
- No `paper=False` client path in project APIs.
- No custom broker base URL setting.
- No short selling.
- No leverage.
- No margin usage.
- No fractional shares.
- No non-SPY assets.
- No notional, limit, stop, stop-limit, trailing-stop, bracket, OCO, OTO, extended-hours, cancellation, replacement, or liquidation behavior.

## Duplicate and Timeout Behavior

- Duplicate protection is durable in SQLite and survives repository/service/process recreation.
- The service reserves IDs before broker submission.
- Existing broker orders found by `client_order_id` are reconciled into the local ledger without a second submission.
- A timeout, transport uncertainty, cancellation, or malformed uncertain response marks `submission_unknown`.
- Uncertain submissions are not retried automatically.
- Explicit reconciliation performs lookup only and never submits.

## API Route Inventory

Existing Phase 7 read routes are preserved. Phase 8 adds:

- `GET /api/v1/paper-trading/status`
- `GET /api/v1/paper-orders`
- `GET /api/v1/paper-orders/{client_order_id}`

All application routes remain read-only. The API never constructs an Alpaca client, contacts Alpaca, changes the kill switch, approves orders, submits orders, cancels orders, replaces orders, or mutates broker state. Unknown client-order IDs return structured 404. Corrupted execution records return sanitized 503. Credential state is exposed only as booleans.

## Dashboard Inventory

- Added read-only `Paper Trading Status` tab.
- The dashboard consumes only FastAPI responses.
- It does not import execution repositories, query SQLite directly, import Alpaca, construct an Alpaca client, or contact Alpaca.
- It shows educational warnings, execution mode, paper-execution enabled state, dry-run state, kill-switch state, credential presence booleans, latest local attempt status, unresolved submission count, and recent local paper-order attempts with pagination labels.
- It has no approve, submit, retry, reconcile, enable, disable, cancel, replace, or liquidation controls.

## Redaction Behavior

- Settings display safe values expose `alpaca_api_key_present` and `alpaca_secret_key_present` booleans only.
- Full account IDs are fingerprinted before storage.
- API responses and dashboard state never contain secret values or full account identifiers.
- Execution errors use structured project-owned codes and sanitized messages.
- Tests search local storage and error strings for credential exposure.

## Tests Added

- Configuration defaults, live rejection, credential redaction.
- Identifier validation and deterministic fingerprints.
- Approval matching, expiry, and mismatch rejection.
- Execution model finite Decimal and whole-share validation.
- Kill-switch default, explicit disengagement, re-engagement, and audit events.
- v1-to-v2 schema migration, fresh v2 initialization, idempotency path, future-schema rejection.
- Ledger attempt round trips, event ordering, duplicate constraints, tampered rows, and corrupted kill switch.
- Service gates for defaults, dry run, missing credentials, live mode, kill switch, stale market state, unsafe broker environment, blocked accounts, unsafe account configuration, existing positions, conflicting open orders, successful submit, duplicate submit, existing broker order, timeout, and reconciliation.
- Alpaca adapter construction, request mapping, response validation, SDK exception translation, and no retry on submit exception.
- API status/list/detail, pagination, route inventory, structured 404, sanitized 503, and no broker client import.
- Dashboard read-only paper status rendering, redaction, unavailable state, pagination labels, and no direct SQLite/Alpaca adapter import.
- Public import-boundary tests for package imports without Alpaca imports or file creation.
- Phase 3-8 integration flow with deterministic artifacts, fake broker accepted submission, duplicate protection after repository reopen, FastAPI readback, dashboard state load, and no credential persistence.
- Separate uncertain-submission integration path with timeout, `submission_unknown`, no second submit, and lookup-only reconciliation.

## Baseline Verification

Commands run before Phase 8 implementation:

- `python -m pip install -e ".[dev]"`: passed
- `pytest`: passed, 539 tests, 5 warnings, 81% full-suite coverage
- `pytest tests/unit -q`: passed, existing unit suite, 5 warnings, 81% coverage
- `pytest tests/integration -q`: passed, 5 tests, 5 warnings, 71% integration-only coverage
- `ruff check .`: passed
- `ruff format --check .`: passed, 93 files already formatted
- `mypy src tests`: passed, 84 source files
- `python -c "import spy_market_agent; print(spy_market_agent.__version__)"`: `0.1.0`
- Public export smoke checks for `strategies`, `risk`, `backtesting`, `persistence`, `api`, and `dashboard`: passed
- `git diff --check`: passed

## In-Progress Verification

Commands run during implementation:

- `python -m pip install -e ".[dev]"`: passed; installed `alpaca-py` `0.43.5`
- `pytest tests/unit/test_execution_models.py tests/unit/test_execution_settings.py tests/unit/test_execution_repository.py tests/unit/test_execution_service.py tests/unit/test_alpaca_paper_adapter.py tests/unit/test_api_phase8.py tests/unit/test_dashboard_phase7.py tests/unit/test_public_phase7_api.py -q`: passed
- `pytest tests/integration/test_phase8_paper_execution_flow.py -q`: passed, 2 tests
- `pytest`: passed, 613 tests, 6 warnings, 81% full-suite coverage
- `pytest tests/unit -q`: passed, 81% coverage, 6 warnings
- `pytest tests/integration -q`: passed, 7 tests, 5 warnings, 69% integration-only coverage
- `ruff check` on edited source/tests: passed
- `mypy src tests`: passed, 100 source/test files

## Final Verification

Commands run after implementation and documentation:

- `python -m pip install -e ".[dev]"`: passed; editable install completed and `alpaca-py` `0.43.5` was present.
- `pytest`: passed, 613 tests, 6 warnings, 81% full-suite coverage, 73.42 seconds.
- `pytest tests/unit -q`: passed, 6 warnings, 81% coverage.
- `pytest tests/integration -q`: passed, 7 tests, 5 warnings, 69% integration-only coverage.
- `ruff check .`: passed, `All checks passed!`
- `ruff format --check .`: passed, `110 files already formatted`
- `mypy src tests`: passed, `Success: no issues found in 100 source files`
- `python -c "import alpaca; import importlib.metadata as m; print(m.version('alpaca-py'))"`: `0.43.5`
- `python -c "import spy_market_agent; print(spy_market_agent.__version__)"`: `0.1.0`
- `python -c "import spy_market_agent.strategies as m; print(sorted(m.__all__))"`: passed; Phase 3-7 strategy exports unchanged.
- `python -c "import spy_market_agent.risk as m; print(sorted(m.__all__))"`: passed; Phase 3-7 risk exports unchanged.
- `python -c "import spy_market_agent.backtesting as m; print(sorted(m.__all__))"`: passed; Phase 6 backtesting exports unchanged.
- `python -c "import spy_market_agent.persistence as m; print(sorted(m.__all__))"`: passed; public persistence exports unchanged apart from the v2 schema value behind the existing constant.
- `python -c "import spy_market_agent.execution as m; print(sorted(m.__all__))"`: passed; broker-independent execution exports available and `AlpacaPaperBroker` is not exported through `__all__`.
- `python -c "import spy_market_agent.api as m; print(sorted(m.__all__))"`: passed; Phase 8 read-response schemas and read-service protocol are exported.
- `python -c "import spy_market_agent.dashboard as m; print(sorted(m.__all__))"`: passed; dashboard public exports unchanged.
- `git diff --check`: passed.

Explicit smoke checks:

- `pytest tests/unit/test_public_phase7_api.py::test_import_boundaries_do_not_import_alpaca_or_create_files tests/unit/test_api_phase8.py::test_api_factory_health_and_get_requests_do_not_create_database_or_broker_client tests/unit/test_api_phase8.py::test_phase8_api_route_inventory_has_no_state_changing_application_routes tests/unit/test_dashboard_phase7.py::test_dashboard_import_smoke_public_exports_and_no_database_access tests/unit/test_dashboard_phase7.py::test_dashboard_paper_status_view_is_read_only_and_redacted tests/unit/test_alpaca_paper_adapter.py::test_alpaca_client_is_constructed_paper_only_without_custom_url tests/unit/test_alpaca_paper_adapter.py::test_market_day_spy_order_request_mapping_and_response_validation tests/unit/test_alpaca_paper_adapter.py::test_submit_sdk_exception_becomes_uncertain_without_retry tests/unit/test_execution_service.py::test_live_mode_request_at_execution_boundary_raises_runtime_error tests/unit/test_execution_service.py::test_timeout_marks_submission_unknown_and_reconciliation_never_submits -q`: passed, 16 tests, 2 warnings.
- The smoke checks prove package import, execution import, FastAPI factory/startup/GET requests, dashboard import/rendering, and read-only route inventory do not construct a broker client, submit an order, or create/migrate SQLite files.
- The adapter checks prove `TradingClient` is constructed with `paper=True`, no caller-provided base URL or `paper` override is accepted, and submit exceptions are not retried.
- The service checks prove `execution_mode="live"` is rejected at the execution boundary and a timeout cannot cause a duplicate submission.

Source and behavior audit:

- `rg "paper=False|https://api\\.alpaca\\.markets|api\\.alpaca\\.markets|@(?:app|router)\\.(?:post|put|patch|delete)" src tests`: only the canonical paper endpoint appears in executable source; the live endpoint appears only in a rejection test.
- No API state-changing application route was found by behavior tests or source audit.
- No dashboard execution control was found by behavior tests.

Coverage and warnings:

- Final full-suite coverage: 81%.
- Final full-suite warnings: 6 third-party warnings from `exchange_calendars`, `fastapi`/Starlette TestClient, and `websockets`; no warnings were suppressed.

Git status and diff summary:

- `git status --short`: expected Phase 8 changes only; 19 tracked files modified and 17 new files untracked before staging.
- `git diff --check`: passed.
- `git diff --stat`: tracked-file working diff showed 19 files changed, 813 insertions, 43 deletions.
- `git diff --stat origin/main...HEAD`: no output before commit because the review branch had no committed Phase 8 changes yet.
- `git diff --cached --stat`: staged diff showed 36 files changed, 5624 insertions, 43 deletions.

## Known Limitations

- Phase 8 supports explicit Alpaca paper-order submission only through service calls; there are no API or dashboard execution controls.
- Paper fills can differ from historical next-open backtest assumptions and from live fills.
- Reconciliation is explicit and lookup-only.
- There is no market-data downloading, scheduler, background worker, deployment configuration, authentication, order cancellation, order replacement, liquidation helper, live endpoint, or live-money trading support.
- The default committed configuration cannot submit an order.

## Confirmations

- Main was not modified.
- Phase 9 was not started.
- No live trading, live endpoint, `paper=False` client path, short selling, leverage, margin, fractional shares, non-SPY asset, scheduler, background worker, deployment, authentication, API write route, dashboard execution control, order cancellation, or order replacement was added.

## Phase 8 Correction Addendum

Correction branch: `review/phase-08-corrections`.

Starting main SHA: `d5e2a81ed51951b414100e440796397cb3cbd938`.

Original Phase 8 implementation SHA: `72d2caed82a30b6710b8b14e24920def3406d53a`.

Cherry-picked Phase 8 implementation SHA on correction branch: `b7062746a22e6ff3fb429f86a4ad6cb6f04520f2`.

Final correction commit SHA: reported in the final Codex response after the commit is created and pushed.

Review findings corrected:

- Added a final durable kill-switch reread immediately before broker submission.
- Separated definitive broker rejection from uncertain post-submit outcomes.
- Replaced broker lookup receipts with broker-only order snapshots.
- Bound reconciliation lineage only from persisted local attempts.
- Added repository-level receipt lineage and state-transition validation.
- Added missing cross-field quantity relationship checks.

Files created:

- None.

Files modified:

- `README.md`
- `reviews/PHASE_08_REVIEW.md`
- `src/spy_market_agent/execution/__init__.py`
- `src/spy_market_agent/execution/alpaca_paper.py`
- `src/spy_market_agent/execution/errors.py`
- `src/spy_market_agent/execution/models.py`
- `src/spy_market_agent/execution/protocols.py`
- `src/spy_market_agent/execution/repository.py`
- `src/spy_market_agent/execution/service.py`
- `tests/integration/test_phase8_paper_execution_flow.py`
- `tests/unit/phase8_helpers.py`
- `tests/unit/test_alpaca_paper_adapter.py`
- `tests/unit/test_execution_models.py`
- `tests/unit/test_execution_repository.py`
- `tests/unit/test_execution_service.py`

Final kill-switch ordering:

- The early kill-switch check is preserved.
- After broker preflights, execution-time risk approval, durable reservation, and broker lookup by `client_order_id`, the service rereads the durable kill switch.
- If no existing broker order is found and the final check passes, the next broker operation is `submit_market_day_order`.
- If the final check finds an engaged, missing, corrupted, unavailable, or uncertain kill-switch state, the service blocks the reserved attempt, retains the IDs, appends an audit event when safely possible, and raises `PaperExecutionKillSwitchError`.

Submission-outcome taxonomy:

- Definitive local/pre-submit failures do not call the broker and do not become `submission_unknown`.
- Definitive broker rejection uses `PaperExecutionBrokerRejectionError`, records `rejected`, retains identifiers, and is never retried automatically.
- Timeout, connection loss, cancellation, unknown SDK failure, malformed returned order, contradictory returned order, missing response fields, and response-validation mismatches become `submission_unknown`, retain identifiers, and require explicit reconciliation.

BrokerOrderSnapshot design:

- `BrokerOrderSnapshot` contains only broker-observable fields: broker order ID, client-order ID, broker status, symbol, side, submitted quantity, filled quantity, order type, time in force, extended-hours flag, timestamps, safe request ID, and execution environment.
- It contains no `signal_id`, no `approval_id`, no instruction fingerprint, and no locally manufactured lineage.

Reconciliation lineage rules:

- Broker lookup returns `BrokerOrderSnapshot | None`.
- The service retrieves the local attempt by `client_order_id`.
- Broker snapshots must match persisted client-order ID, SPY symbol, side, whole-share quantity, market order type, DAY time in force, `extended_hours=False`, and supported paper environment.
- `PaperOrderReceipt` lineage is built from persisted signal ID, fingerprint, approval ID, and schema fields, never from broker fields or client-order ID derivation.
- Mismatching broker snapshots do not submit, do not reconcile, retain the reservation, mark the attempt unresolved, and append a safe mismatch event.

Repository defence-in-depth:

- `record_receipt` loads the persisted attempt inside the same transaction.
- It verifies signal ID, client-order ID, instruction fingerprint, symbol, side, quantity, market/DAY/regular-hours contract, and permitted prior state.
- It checks that exactly one row is updated.
- On mismatch, it rolls back, leaves broker fields unchanged, and does not append success or reconciliation events.
- Event lineage is built from the persisted attempt rather than untrusted receipt fields.

Quantity relationship validation:

- Position `available_quantity` must not exceed `quantity`; zero positions must have zero available quantity.
- Open-order `filled_quantity` must not exceed submitted quantity.
- Broker-order snapshot `filled_quantity`, when present, must not exceed submitted quantity.
- Paper-order receipt `filled_quantity`, when present, must not exceed submitted quantity.
- Existing finite, nonnegative, whole-share, NaN, and infinity checks remain in place.

Regression tests added:

- Final kill-switch race after reservation.
- Final kill-switch read failure after reservation.
- Final kill-switch ordering before submit.
- Existing matching broker order without final submit gate.
- Definitive broker rejection recorded as `rejected`.
- Timeout, connection loss, cancellation, and unknown SDK failures recorded as `submission_unknown`.
- Malformed or contradictory post-submit snapshots recorded as `submission_unknown`.
- Broker lookup snapshot without local lineage.
- Matching and mismatching existing broker-order reconciliation.
- Terminal attempts rejected from reconciliation.
- Forged receipt lineage rejected transactionally by the repository.
- Position, open-order, broker-snapshot, and receipt quantity relationship checks.

Baseline verification on the correction branch before edits:

- `python -m pip install -e ".[dev]"`: passed; `alpaca-py` `0.43.5` present.
- `pytest`: `613 passed, 6 warnings in 73.13s`, coverage `81%`.
- `pytest tests/unit -q`: passed, `6 warnings`, coverage `81%`.
- `pytest tests/integration -q`: `7 passed`, `5 warnings`, integration-only coverage `69%`.
- `ruff check .`: `All checks passed!`
- `ruff format --check .`: `110 files already formatted`
- `mypy src tests`: `Success: no issues found in 100 source files`
- `python -c "import alpaca; import importlib.metadata as m; print(m.version('alpaca-py'))"`: `0.43.5`
- `python -c "import spy_market_agent; print(spy_market_agent.__version__)"`: `0.1.0`
- Baseline execution, persistence, API, and dashboard export smoke checks: passed.
- `git diff --check`: passed.

In-progress correction verification:

- `pytest tests/unit/test_execution_models.py tests/unit/test_execution_repository.py tests/unit/test_execution_service.py tests/unit/test_alpaca_paper_adapter.py tests/integration/test_phase8_paper_execution_flow.py -q`: passed, 99 tests, 6 warnings.
- `pytest tests/unit/test_api_phase8.py tests/unit/test_dashboard_phase7.py tests/unit/test_public_phase7_api.py -q`: passed, 34 tests, 1 warning.
- `ruff check .`: passed after mechanical cleanup.
- `mypy src tests`: passed, 100 source files.

Final verification:

- `python -m pip install -e ".[dev]"`: passed; editable `spy-market-agent 0.1.0` installed and `alpaca-py 0.43.5` was present.
- `pytest`: `657 passed, 6 warnings in 76.21s`, full-suite coverage `81%`.
- `pytest tests/unit -q`: passed with coverage `81%`; supplementary `pytest tests/unit -q --no-cov` confirmed the 646-test unit suite and the same six warnings.
- `pytest tests/integration -q`: 11 integration tests passed, 5 warnings, integration-only coverage `69%`.
- `ruff check .`: `All checks passed!`
- `ruff format --check .`: `110 files already formatted`
- `mypy src tests`: `Success: no issues found in 100 source files`
- `python -c "import alpaca; import importlib.metadata as m; print(m.version('alpaca-py'))"`: `0.43.5`
- `python -c "import spy_market_agent; print(spy_market_agent.__version__)"`: `0.1.0`
- `python -c "import spy_market_agent.strategies as m; print(sorted(m.__all__))"`: passed; exports unchanged.
- `python -c "import spy_market_agent.risk as m; print(sorted(m.__all__))"`: passed; exports unchanged.
- `python -c "import spy_market_agent.backtesting as m; print(sorted(m.__all__))"`: passed; exports unchanged.
- `python -c "import spy_market_agent.persistence as m; print(sorted(m.__all__))"`: passed; exports unchanged.
- `python -c "import spy_market_agent.execution as m; print(sorted(m.__all__))"`: passed; exports now include `BrokerOrderSnapshot` and `PaperExecutionBrokerRejectionError`.
- `python -c "import spy_market_agent.api as m; print(sorted(m.__all__))"`: passed; read-only API exports unchanged apart from Phase 8 additions.
- `python -c "import spy_market_agent.dashboard as m; print(sorted(m.__all__))"`: passed; dashboard exports unchanged.
- `git diff --check`: passed.

Explicit correction smoke checks:

- `pytest tests/unit/test_public_phase7_api.py::test_import_boundaries_do_not_import_alpaca_or_create_files tests/unit/test_api_phase8.py::test_api_factory_health_and_get_requests_do_not_create_database_or_broker_client tests/unit/test_api_phase8.py::test_phase8_api_route_inventory_has_no_state_changing_application_routes tests/unit/test_dashboard_phase7.py::test_dashboard_import_smoke_public_exports_and_no_database_access tests/unit/test_dashboard_phase7.py::test_dashboard_paper_status_view_is_read_only_and_redacted tests/unit/test_alpaca_paper_adapter.py::test_alpaca_client_is_constructed_paper_only_without_custom_url tests/unit/test_alpaca_paper_adapter.py::test_market_day_spy_order_request_mapping_and_response_validation tests/unit/test_alpaca_paper_adapter.py::test_submit_sdk_exception_becomes_uncertain_without_retry tests/unit/test_alpaca_paper_adapter.py::test_adapter_post_submit_response_mismatches_are_unknown tests/unit/test_alpaca_paper_adapter.py::test_lookup_returns_broker_snapshot_without_local_lineage tests/unit/test_execution_service.py::test_live_mode_request_at_execution_boundary_raises_runtime_error tests/unit/test_execution_service.py::test_timeout_marks_submission_unknown_and_reconciliation_never_submits tests/unit/test_execution_service.py::test_definitive_broker_rejection_records_rejected_without_retry tests/unit/test_execution_service.py::test_final_kill_switch_reread_blocks_after_reservation_and_keeps_ids tests/unit/test_execution_service.py::test_reconciliation_rejects_mismatch_and_never_submits tests/unit/test_execution_repository.py::test_record_receipt_rejects_forged_or_mismatched_lineage_transactionally -q`: `36 passed, 2 warnings`.
- Smoke coverage proves imports, FastAPI factory/startup/GET requests, and dashboard import/rendering construct no broker client; create or migrate no SQLite file; make no external network request; submit no order automatically; expose no API write route; expose no dashboard execution control; reject live execution mode; never automatically retry submit; classify uncertainty after submit as `submission_unknown`; use `rejected` only for definitive rejection; keep broker lookup lineage-free; reconcile without submit; block final kill-switch engagement; and reject forged receipts transactionally.
- Source audit for `paper=False`, live Alpaca endpoint support, API write decorators, cancellation, replacement, liquidation, schedulers, background workers, and dashboard execution controls found only expected documentation/test references and the canonical paper-only adapter construction `TradingClient(..., paper=True)`.
- `git status --short`: listed only expected correction files as modified: `README.md`, `reviews/PHASE_08_REVIEW.md`, the execution correction modules, and the Phase 8 correction tests.
- `git diff --stat origin/main...HEAD`: 36 files changed, 5625 insertions, 43 deletions at the pre-commit review point.
- `git diff --check`: passed.

Coverage:

- Baseline full-suite coverage: `81%`.
- Final full-suite coverage: `81%`.

Warnings:

- Baseline warnings were the existing third-party warnings from `exchange_calendars`, FastAPI/Starlette TestClient, and `websockets`.
- No warnings were suppressed.

Known limitations:

- Explicit reconciliation is lookup-only and does not submit.
- Engaging the kill switch after the final pre-submit check cannot cancel an already in-flight broker request because cancellation remains outside Phase 8.
- There are still no API or dashboard execution controls.
- There is no live endpoint, scheduler, deployment, authentication, cancellation, replacement, or liquidation support.

Correction confirmations:

- Main was not modified.
- The original Phase 8 branch `review/phase-08-paper-trading-preparation` was not modified.
- Phase 9 was not started.
- No live trading, live endpoint, `paper=False` client, automatic execution, submission retry, short selling, leverage, margin, fractional shares, non-SPY asset, scheduler, background worker, deployment, authentication, API write route, dashboard execution control, cancellation, replacement, or liquidation behavior was added.

## Phase 8 Final Hardening Addendum

Final-hardening branch name:

- `review/phase-08-final-hardening`

Starting main SHA:

- `d5e2a81ed51951b414100e440796397cb3cbd938`

Original implementation and correction SHAs:

- Original Phase 8 implementation SHA: `b7062746a22e6ff3fb429f86a4ad6cb6f04520f2`
- Original Phase 8 correction SHA: `1065ab74c6d1ac3aa4f41657533d394b9c52ac03`

New cherry-picked SHAs on the final-hardening branch:

- New cherry-picked implementation SHA: `f9a794cdf2ffb2dc9f3f7c5044bde131cc86940e`
- New cherry-picked correction SHA: `f6d9a65d143e0fd910ffbcc0caf9496754278be5`

Final hardening commit SHA:

- Reported in the final Codex response after the commit is created and pushed.

Findings corrected:

- Real Alpaca SDK enum values are normalized through their `.value` strings for account status, asset class, and position side.
- Local Alpaca request-construction failures are distinguished from uncertain post-submit outcomes.
- The SQLite execution ledger independently enforces allowed state transitions and persisted lineage.
- The SQLite execution ledger independently rejects any receipt environment other than `alpaca_paper`.

Files created:

- None.

Files modified:

- `README.md`
- `reviews/PHASE_08_REVIEW.md`
- `src/spy_market_agent/execution/__init__.py`
- `src/spy_market_agent/execution/alpaca_paper.py`
- `src/spy_market_agent/execution/errors.py`
- `src/spy_market_agent/execution/repository.py`
- `src/spy_market_agent/execution/service.py`
- `tests/integration/test_phase8_paper_execution_flow.py`
- `tests/unit/test_alpaca_paper_adapter.py`
- `tests/unit/test_api_phase8.py`
- `tests/unit/test_execution_repository.py`
- `tests/unit/test_execution_service.py`

SDK enum normalization behavior:

- `AccountStatus.ACTIVE` becomes `ACTIVE` and `AccountStatus.INACTIVE` becomes `INACTIVE`.
- `AssetClass.US_EQUITY` becomes `us_equity`.
- `PositionSide.LONG` becomes `long` and `PositionSide.SHORT` becomes `short`.
- Existing strict conversions for asset status, order side, order type, time in force, and order status remain in place.
- Malformed enum-like objects fail closed through project-owned broker errors.

Local request-construction error taxonomy:

- Added `PaperExecutionBrokerRequestError` for failures while building the local Alpaca `MarketOrderRequest`.
- The adapter constructs the fixed SPY market DAY order request before entering the protected SDK submit call.
- Unsupported local side, invalid local quantity, local request-model validation failure, and expected conversion failures raise `PaperExecutionBrokerRequestError`.
- These failures mean `TradingClient.submit_order` was not called, so they are recorded as `blocked`, not `submission_unknown`.
- Reserved signal, client-order, and approval IDs remain retained and cannot be reused silently.
- Failures after the SDK submit call may have started retain the existing unknown-submission taxonomy.

Ledger transition matrix:

- Receipt transitions: `reserved -> accepted`, `reserved -> broker_existing_order_found`, `reserved -> reconciled`, and `submission_unknown -> reconciled`.
- Unknown-outcome transitions: `reserved -> submission_unknown` and `submission_unknown -> submission_unknown`.
- Failure transitions: `reserved -> blocked` and `reserved -> rejected`.
- Terminal states `accepted`, `broker_existing_order_found`, `reconciled`, `rejected`, and `blocked` cannot transition through `mark_submission_unknown()` or `mark_failure()`.
- `mark_failure()` rejects every target state except `blocked` and `rejected`.

Persisted-lineage enforcement:

- `mark_submission_unknown()` and `mark_failure()` validate supplied identifiers before opening a transaction, then load the persisted attempt and require the supplied signal ID to match the persisted signal ID.
- Audit event lineage is built from persisted attempt rows, not caller-supplied fallback values.
- `record_receipt()` validates receipt signal ID, client-order ID, fingerprint, SPY symbol, side, whole-share quantity, order type, time in force, regular-hours flag, paper environment, and permitted prior state.
- SQL updates must affect exactly one row.

Paper-environment receipt validation:

- Repository receipt validation now requires `receipt.execution_environment == "alpaca_paper"`.
- Forged environments such as `alpaca_live`, `live`, `production`, `paper`, and `unknown` are rejected with a sanitized `receipt_environment_mismatch` integrity error.
- Rejected forged receipts do not update attempt status or broker fields and do not append success or reconciliation events.

Regression tests added:

- Real alpaca-py enum normalization for account status, asset class, asset status, and position side.
- Full enum-backed Alpaca preflight integration path with exactly one fake paper order submission.
- Malformed enum-like value rejection.
- Local `MarketOrderRequest` construction failure with zero submit calls.
- Unsupported local side and invalid local quantity blocked before submit.
- Service-level blocked local request-construction failure with retained identifiers.
- API visibility for blocked local request-construction failure.
- Repository state-machine transitions for `submission_unknown`, `blocked`, and `rejected`.
- Terminal-state regression rejection.
- Wrong signal-lineage rejection for unknown and failure updates.
- Row-count mismatch and SQLite failure rollback.
- Paper-environment receipt enforcement and forged live receipt rejection.
- Integration coverage for terminal-state protection, wrong signal lineage, and forged live receipt rollback.

Baseline verification before final hardening edits:

- `python -m pip install -e ".[dev]"`: passed; editable package installed with `alpaca-py 0.43.5`.
- `pytest`: `657 passed, 6 warnings in 74.71s`; full-suite coverage `81%`.
- `pytest tests/unit -q`: passed with coverage `81%` and the same six warnings; merged suite composition was 646 unit tests and 11 integration tests.
- `pytest tests/integration -q`: `11 passed, 5 warnings`; integration-only coverage `69%`.
- `ruff check .`: `All checks passed!`
- `ruff format --check .`: `110 files already formatted`
- `mypy src tests`: `Success: no issues found in 100 source files`
- `python -c "import alpaca; import importlib.metadata as m; print(m.version('alpaca-py'))"`: `0.43.5`
- `python -c "from alpaca.trading.enums import AccountStatus, AssetClass, AssetStatus, PositionSide; print(AccountStatus.ACTIVE.value, AssetClass.US_EQUITY.value, AssetStatus.ACTIVE.value, PositionSide.LONG.value)"`: `ACTIVE us_equity active long`
- `python -c "import spy_market_agent; print(spy_market_agent.__version__)"`: `0.1.0`
- Package export smoke checks for `strategies`, `risk`, `backtesting`, `persistence`, `execution`, `api`, and `dashboard`: passed.
- `git diff --check`: passed.

Final verification:

- `python -m pip install -e ".[dev]"`: passed; editable `spy-market-agent 0.1.0` installed and `alpaca-py 0.43.5` was present.
- `pytest`: `700 passed, 6 warnings in 77.89s`; full-suite coverage `82%`.
- `pytest tests/unit -q`: passed with coverage `82%` and 6 warnings. Supplemental `pytest tests/unit --collect-only -qq --no-cov` confirmed 685 collected unit tests.
- `pytest tests/integration -q`: 15 integration tests passed, 6 warnings, integration-only coverage `71%`.
- `ruff check .`: `All checks passed!`
- `ruff format --check .`: `110 files already formatted`
- `mypy src tests`: `Success: no issues found in 100 source files`
- `python -c "import alpaca; import importlib.metadata as m; print(m.version('alpaca-py'))"`: `0.43.5`
- `python -c "from alpaca.trading.enums import AccountStatus, AssetClass, AssetStatus, PositionSide; print(AccountStatus.ACTIVE.value, AssetClass.US_EQUITY.value, AssetStatus.ACTIVE.value, PositionSide.LONG.value)"`: `ACTIVE us_equity active long`
- `python -c "import spy_market_agent; print(spy_market_agent.__version__)"`: `0.1.0`
- `python -c "import spy_market_agent.strategies as m; print(sorted(m.__all__))"`: passed; exports unchanged.
- `python -c "import spy_market_agent.risk as m; print(sorted(m.__all__))"`: passed; exports unchanged.
- `python -c "import spy_market_agent.backtesting as m; print(sorted(m.__all__))"`: passed; exports unchanged.
- `python -c "import spy_market_agent.persistence as m; print(sorted(m.__all__))"`: passed; exports unchanged.
- `python -c "import spy_market_agent.execution as m; print(sorted(m.__all__))"`: passed; exports include `PaperExecutionBrokerRequestError`.
- `python -c "import spy_market_agent.api as m; print(sorted(m.__all__))"`: passed; API exports unchanged.
- `python -c "import spy_market_agent.dashboard as m; print(sorted(m.__all__))"`: passed; dashboard exports unchanged.
- `git diff --check`: passed.

Explicit targeted hardening and smoke checks:

- `pytest tests/unit/test_alpaca_paper_adapter.py tests/unit/test_execution_repository.py tests/unit/test_execution_service.py tests/unit/test_api_phase8.py tests/unit/test_public_phase7_api.py tests/unit/test_dashboard_phase7.py tests/integration/test_phase8_paper_execution_flow.py -q --no-cov`: 148 tests passed, 6 warnings.
- This targeted set covers real enum-value normalization, enum-backed preflight success, local request-construction failure with zero submit calls, blocked local request failure rather than `submission_unknown`, retained IDs, terminal ledger-state protection, wrong signal-lineage rejection, persisted event lineage, forged `alpaca_live` receipt rejection, rollback after failed repository operations, generic post-submit uncertainty as `submission_unknown`, no automatic submit retry, no broker clients on import/API/dashboard startup or GET/render paths, no SQLite creation/migration on those read-only paths, no external network request, no automatic order submission, no public live-client construction, no API write route, and no dashboard execution control.

Source and behavior audit:

- `rg -n "paper=False|paper = False|live-api\\.alpaca|api\\.alpaca\\.markets|@.*\\.(post|put|patch|delete)\\(" src tests README.md PROJECT_SPEC.md reviews/PHASE_08_REVIEW.md`: only expected documentation/review references, the canonical paper endpoint, and the live-environment rejection test were found.
- `rg -n "cancel|replace|liquidat|scheduler|background|cron|websocket|POST|PUT|PATCH|DELETE" src/spy_market_agent/execution src/spy_market_agent/api src/spy_market_agent/dashboard README.md PROJECT_SPEC.md reviews/PHASE_08_REVIEW.md`: only expected scope documentation, the read-only route inventory guard, harmless timestamp `.replace("+00:00", "Z")` calls, and existing third-party warning text were found.
- Behavior tests confirmed the adapter always passes `paper=True`, callers cannot override the broker URL through a public project API, `execution_mode="live"` is rejected, `submit_order` is never automatically retried, and post-submit uncertainty cannot cause a duplicate submission.

Final git audit before commit:

- `git status --short`: expected modified files only: `README.md`, `reviews/PHASE_08_REVIEW.md`, `src/spy_market_agent/execution/__init__.py`, `src/spy_market_agent/execution/alpaca_paper.py`, `src/spy_market_agent/execution/errors.py`, `src/spy_market_agent/execution/repository.py`, `src/spy_market_agent/execution/service.py`, `tests/integration/test_phase8_paper_execution_flow.py`, `tests/unit/test_alpaca_paper_adapter.py`, `tests/unit/test_api_phase8.py`, `tests/unit/test_execution_repository.py`, and `tests/unit/test_execution_service.py`.
- `git diff --stat origin/main...HEAD`: 36 files changed, 7058 insertions, 43 deletions.
- `git diff --check`: passed.

Coverage:

- Baseline full-suite coverage: `81%`.
- Final full-suite coverage: `82%`.

Warnings:

- Baseline warnings: 6 existing third-party warnings.
- Final warnings: 6 existing third-party warnings from `exchange_calendars`, FastAPI/Starlette TestClient, and `websockets`. No warnings were suppressed.

Known limitations:

- Phase 8 remains paper-only and explicitly invoked.
- Local request-construction failures block the reserved attempt but do not release IDs.
- Reconciliation remains lookup-only and never submits.
- Engaging the kill switch after the final pre-submit check cannot cancel an already in-flight broker request.
- API and dashboard views remain read-only and cannot approve, submit, reconcile, retry, cancel, replace, liquidate, or change the kill switch.

Confirmation after final hardening commit:

- Main was not modified.
- Both earlier Phase 8 branches were not modified.
- Phase 9 was not started.
- No live trading, live endpoint, `paper=False` client, automatic execution, automatic submission retry, short selling, leverage, margin, fractional shares, non-SPY asset, scheduler, background worker, deployment, authentication, API write route, dashboard execution control, cancellation, replacement, or liquidation behavior was added.
