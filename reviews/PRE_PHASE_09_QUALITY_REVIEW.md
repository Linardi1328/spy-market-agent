# Pre-Phase 9 Quality Review

## Scope

Perform a warning audit and coverage cleanup after Phase 8 was merged and before any Phase 9 work begins.

This pass did not add Phase 9 functionality and did not change Phase 8 execution behavior.

## Branch

- Starting main SHA: `846db31158723d43a2aa66004e2d31e0beb20378`
- Branch: `review/pre-phase-09-quality-cleanup`
- Confirmed merged Phase 8 concurrency commit: `ae3d390` is an ancestor of `origin/main`.

## Baseline Verification

- `python -m pip install -e ".[dev]"`: passed; editable `spy-market-agent 0.1.0` installed.
- `pytest`: `758 passed, 6 warnings`; full-suite coverage displayed as `82%`.
- `ruff check .`: `All checks passed!`
- `ruff format --check .`: `111 files already formatted`
- `mypy src tests`: `Success: no issues found in 101 source files`

## Warning Audit

Diagnostic commands:

- `pytest -W always -ra`: `758 passed, 7 warnings`.
- `pytest -W error::DeprecationWarning --maxfail=1`: failed as expected while locating an upstream `exchange_calendars` deprecation.
- `pytest -W error::PendingDeprecationWarning --maxfail=1`: `758 passed, 6 warnings`.
- `pytest -W error::FutureWarning --maxfail=1`: initially failed on project use of deprecated scikit-learn `LogisticRegression(penalty="l2")`; passed after the project code change.
- `pytest -W error::ResourceWarning --maxfail=1`: `758 passed, 6 warnings`.

Installed dependency versions recorded during audit:

- `exchange-calendars`: `4.13.2`
- `fastapi`: `0.141.1`
- `starlette`: `1.3.1`
- `httpx`: `0.28.1`
- `websockets`: `16.1.1`
- `scikit-learn`: `1.9.0`
- `pandas`: `2.3.3`
- `numpy`: `2.5.1`

Warnings found:

- Category: `DeprecationWarning`
  - Message: `The 'generic' unit for NumPy timedelta is deprecated, and will raise an error in the future. This includes implicit conversion of bare integers (e.g. `+ 1`).Please use a specific unit instead.`
  - Originating module: `exchange_calendars.exchange_calendar`
  - Triggering test path observed: import during market-calendar-backed tests, including `tests/integration/test_market_data_provider_flow.py`
  - Dependency: `exchange-calendars 4.13.2` with `numpy 2.5.1`
  - Resolution: exact category/message/module pytest filter because the warning is emitted by upstream import code before project code can avoid it.

- Category: `DeprecationWarning`
  - Message: `The 'generic' unit for NumPy timedelta is deprecated, and will raise an error in the future. This includes implicit conversion of bare integers (e.g. `+ 1`).Please use a specific unit instead.`
  - Originating module: `exchange_calendars.utils.pandas_utils`
  - Triggering test path observed: `tests/integration/test_market_data_provider_flow.py::test_fake_provider_can_implement_protocol_without_network_access`
  - Dependency: `exchange-calendars 4.13.2` with `numpy 2.5.1`
  - Resolution: exact category/message/module pytest filter because the warning is emitted by upstream calendar utility code.

- Category: `starlette.exceptions.StarletteDeprecationWarning`
  - Message: `Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.`
  - Originating module: `fastapi.testclient`
  - Triggering tests: FastAPI `TestClient` imports and Phase 7/8 API tests.
  - Dependencies: `fastapi 0.141.1`, `starlette 1.3.1`, `httpx 0.28.1`
  - Resolution: exact category/message/module pytest filter. Project tests use FastAPI's documented `TestClient` entry point, and the compatible migration path is an upstream FastAPI/Starlette/httpx2 transition.

- Category: `DeprecationWarning`
  - Message: `websockets.legacy is deprecated; see https://websockets.readthedocs.io/en/stable/howto/upgrade.html for upgrade instructions`
  - Originating module: `websockets.legacy`
  - Dependency: `websockets 16.1.1`
  - Resolution: exact category/module filter with message anchored to `websockets.legacy`; emitted by upstream import path, not project code.

- Category: `FutureWarning`
  - Message: scikit-learn deprecation for explicit `LogisticRegression(penalty='l2')`
  - Originating module: project modeling code constructing canonical logistic-regression estimators.
  - Triggering test: `tests/integration/test_phase5_modeling_flow.py`
  - Dependency: `scikit-learn 1.9.0`
  - Resolution: removed explicit `penalty="l2"` and updated the deterministic fixed-parameter snapshot to record the equivalent default `classifier.l1_ratio=0.0`.

Pytest warning policy after cleanup:

- All unexpected warnings now fail by default with `filterwarnings = ["error", ...]`.
- The only allowed warning filters are exact documented upstream exceptions by category, message, and module.
- No broad global suppression was added.

## Coverage

Coverage before cleanup:

- Baseline full-suite coverage displayed by `pytest`: `82%`.
- Baseline tests: `758 passed`.

Coverage diagnostics:

- `pytest --cov=src/spy_market_agent --cov-branch --cov-report=term-missing --cov-report=html --cov-report=json`: generated branch coverage reports.
- Intermediate targeted test additions raised full-suite coverage to `83.40261282660333%`.

Coverage after cleanup:

- `pytest --cov-report=json --cov-report=term-missing`: `878 passed`; exact combined coverage `85.3424386381631%`.
- Statement coverage: `88.81596219480178%`.
- Branch coverage: `74.69831053901851%`.
- Covered branches: `1857 / 2486`.
- Full-suite coverage gate target: `pytest --cov-fail-under=85`.

## Tests Added

Added focused regression and coverage tests for:

- Dashboard API client base URL validation, read-only path construction, query parameters, invalid run IDs, HTTP errors, and non-object JSON responses.
- Feature engineering scalar validators, metadata validation, frame-schema validation, dtype validation, non-finite feature rejection, session metadata mismatches, duplicate sessions, and unordered sessions.
- Market-data checksum rejection of noncanonical column order, boolean OHLC values, malformed OHLC values, non-finite OHLC values, boolean volumes, malformed volumes, and non-integral volumes.
- Modeling parameter-reading guards, fitted-state guards, learned array shape checks, finite numeric learned-state checks, estimator object-array checks, probability result conversion, probability row validation, and probability smoke-check failures.
- Persistence serialization readers and writers for required text, optional text, run IDs, dates, datetimes, decimals, booleans, finite floats, integer storage contracts, JSON string tuples, and checksum validation.
- Backtest cost and accounting guardrails for configuration values, scalar validators, execution-price checksum inputs, fill accounting replay, and metrics identity replay.
- Backtest metrics audit validation for invalid frames, malformed portfolio/fill/proposed-order/risk-decision rows, duplicate sequences, order-decision mismatches, and initial-cash mismatch.

## Dependency Changes

- No dependency was added, removed, or upgraded.
- Project-owned warning fix avoided a dependency change by removing deprecated scikit-learn parameter usage.

## Files Modified

- `README.md`
- `pyproject.toml`
- `reviews/PHASE_08_REVIEW.md`
- `reviews/PRE_PHASE_09_QUALITY_REVIEW.md`
- `src/spy_market_agent/modeling/models.py`
- `src/spy_market_agent/modeling/training.py`
- `tests/unit/test_backtest_costs.py`
- `tests/unit/test_backtest_metrics.py`
- `tests/unit/test_dashboard_phase7.py`
- `tests/unit/test_feature_engineering.py`
- `tests/unit/test_market_data_validation.py`
- `tests/unit/test_model_training.py`
- `tests/unit/test_persistence_serialization.py`

## Final Verification

To be completed after documentation updates.

## Confirmations

- Phase 9 was not started.
- No live-trading support was added.
- No API write route was added.
- No dashboard execution control was added.
- Phase 8 paper-only and fail-closed execution boundaries remain unchanged.
