# Version 2 Phase 2 Review

Status: Implementation in review

## Branch

- Starting main SHA: `a53160716ec9b266b9bee899a20855c24c4b7d91`
- Branch name: `review/v2-phase-02-real-benchmark`
- Final implementation SHA (original implementation candidate): `61f1431...`
- Hardening SHA: to be reported after commit/push
- Package/runtime version: `2.0.0a1`
- Target public release identifier: `v2.0.0-alpha.2`
- Git tag status: `v2.0.0-alpha.2` not created

## Scope Implemented

Implemented a dedicated `spy_market_agent.benchmark` package for deterministic, auditable,
file-based Phase 2 benchmark infrastructure. The original implementation candidate at
`61f1431...` accepts verified Phase 1 manifests, records offline feed evidence, checks
dataset eligibility, builds the approved features and labels, constructs the Phase 2
chronological split, writes immutable benchmark locks, runs validation-only model selection,
creates final-test locks, gates final-test access, evaluates locked
baselines/strategies/costs/regimes, writes artifact indexes, and verifies artifacts offline.

This hardening pass strengthens the implementation before owner-run real-data acceptance. It
adds deep semantic verification, frozen runtime-lineage enforcement, real regime-performance
diagnostics, reuse of the approved Version 1 risk/backtest engine for executable long/cash
strategy paths, and immutable final-test access plus separate completion evidence.

## Files Created

- `artifacts/benchmarks/.gitkeep`
- `docs/V2_PHASE_02_BENCHMARK_POLICY.md`
- `docs/V2_PHASE_02_DATA_CARD_TEMPLATE.md`
- `reviews/V2_PHASE_02_REVIEW.md`
- `src/spy_market_agent/benchmark/__init__.py`
- `src/spy_market_agent/benchmark/artifacts.py`
- `src/spy_market_agent/benchmark/baselines.py`
- `src/spy_market_agent/benchmark/cli.py`
- `src/spy_market_agent/benchmark/dataset.py`
- `src/spy_market_agent/benchmark/errors.py`
- `src/spy_market_agent/benchmark/identity.py`
- `src/spy_market_agent/benchmark/locks.py`
- `src/spy_market_agent/benchmark/metrics.py`
- `src/spy_market_agent/benchmark/models.py`
- `src/spy_market_agent/benchmark/pipeline.py`
- `src/spy_market_agent/benchmark/regimes.py`
- `src/spy_market_agent/benchmark/reporting.py`
- `src/spy_market_agent/benchmark/splits.py`
- `src/spy_market_agent/benchmark/strategies.py`
- `src/spy_market_agent/benchmark/verification.py`
- `tests/integration/test_v2_phase2_benchmark_flow.py`
- `tests/unit/test_v2_phase2_benchmark.py`
- `tests/unit/v2_phase2_helpers.py`

## Files Modified

- `.gitignore`
- `AGENTS.md`
- `CHANGELOG.md`
- `FUTURE_ROADMAP.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DEMO_GUIDE.md`
- `docs/REPRODUCIBILITY.md`
- `docs/SECURITY_AND_SAFETY.md`
- `docs/V2_PHASE_02_REAL_HISTORICAL_BENCHMARK_SPEC.md`
- `docs/WORKFLOWS.md`
- `tests/unit/test_phase9_documentation.py`

## Persistence Decision

Phase 2 uses immutable file artifacts under `artifacts/benchmarks/<benchmark_id>/`. The
SQLite schema is unchanged, no migration is added, and no model binary is persisted.

## Policies

- Regime policy: `trend_200`, `realized_volatility_20` with training-only median threshold,
  `drawdown_10`, independent `calendar_year` diagnostics, and locked signal-session
  strategy attribution.
- Split policy: 20-row warm-up, five-session mandatory gap, six-session boundary exclusions,
  70% train, 15% validation, final-test remainder, and fixed minimum row/class counts.
- Cost matrix: `idealized`, `base`, `adverse`, and `severe` with `Decimal("10000")` initial
  cash, zero risk-free rate, no cash yield, whole shares, and no intermediate cents
  quantization.
- Model policy: existing `logistic_regression` and `gradient_boosting` candidates only,
  fixed parameters verified through existing lineage.
- Selection policy: validation ROC AUC, log loss, Brier score, then logistic-regression
  tie-break.
- Classification baselines: `majority_class`, `always_positive`, `always_negative`,
  `training_prevalence`.
- Strategy comparators: `always_cash`, `buy_and_hold`, `fixed_20_session_momentum`, plus the
  selected model using the existing fixed long-or-cash threshold.
- Runtime lineage: Git SHA, Python version, package/runtime version, pandas, pydantic,
  scikit-learn, exchange-calendars, alpaca-py, and benchmark-identity dependencies are
  frozen in the lock and enforced before critical stages.

## Controls

- `benchmark verify` performs deep offline semantic verification for the declared workflow
  stage and rejects semantic tampering even when `artifact_index.json` checksums are
  recomputed.
- Final-test row-level labels are guarded from Stage A services.
- `final_test_access.json` is written before final-test labels are loaded and remains
  immutable started-access evidence.
- `final_test_completion.json` is written only after completed final-test artifacts are
  written and references all required final checksums.
- A completed non-audit final run cannot be silently repeated.
- Audit replay verifies existing final artifacts and does not overwrite accepted results.
- Selected-model and fixed-momentum strategy paths use the approved Version 1
  `StrategySignalSet` -> `ProposedOrder` -> `RiskConfig` / `evaluate_order_risk` -> fill ->
  backtest metric flow.
- Benchmark commands do not make network requests, require credentials, construct Alpaca
  clients, construct broker `TradingClient`, initialize execution databases, or submit
  orders.
- Safe path validation blocks path traversal, artifact-root escapes, source/test/doc/data/Git
  writes, symlink artifacts, and conflicting immutable writes.

## Tests

Test categories include Phase 1 manifest integration, dataset eligibility, feed rules,
split arithmetic, final-test label guards, model configuration snapshots, validation-only
selection, classification baselines, strategy comparators, cost matrix, Decimal accounting,
classification metrics, regimes, deterministic artifact serialization, locks, runtime
lineage mismatch handling, semantic tampering rejection, safe writes,
idempotency/conflict behavior, immutable final-test access/completion, audit replay,
approved risk/backtest engine reuse, no-network/no-broker import safety, CLI behavior,
documentation Quick Start requirements, and existing Version 1/Phase 1 regression flows.

## Verification

Hardening verification run:

- `python -m pip install -e ".[dev]"`: passed.
- `pytest --cov-fail-under=85`: 999 passed, 85.13% coverage.
- `pytest tests/unit -q`: passed; 948 collected unit tests.
- `pytest tests/integration -q`: passed; 51 collected integration tests.
- `pytest -W error::FutureWarning`: 999 passed.
- Targeted Phase 2 tests:
  `pytest tests/unit/test_v2_phase2_benchmark.py tests/integration/test_v2_phase2_benchmark_flow.py -q`:
  21 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.
- `mypy src tests`: passed.
- `git diff --check`: passed.
- Package/runtime version check: `2.0.0a1 2.0.0a1`.
- Local dashboard smoke: not rerun for this hardening pass because README Quick Start and
  startup code paths were not changed.

The previous original implementation candidate recorded 994 passing full tests, 945 unit
tests, 49 integration tests, 16 targeted Phase 2 tests, 85.21% coverage, and passing Ruff,
Ruff format, MyPy, FutureWarning, and local startup smoke checks.

## Known Limitations

- No real Phase 2 benchmark was run by Codex.
- No real final test was accessed.
- No real SPY dataset is distributed or committed.
- No generated real benchmark result is committed.
- Owner-run feed, dataset, validation, final-test authorization, real final benchmark,
  artifact verification, and release-preparation review remain open acceptance gates.

## Explicit Confirmations

- No real benchmark was run by Codex.
- No real final test was accessed.
- No real SPY dataset was committed.
- No generated real benchmark result was committed.
- No credentials or account identifiers were committed.
- No model family or parameter changed.
- No feature or label changed.
- No threshold tuning was added.
- No paper-execution behavior changed.
- No API write route was added.
- No dashboard execution control was added.
- No live support was added.
- Package/runtime version remains `2.0.0a1`.
- `v2.0.0-alpha.2` was not created.
- Phase 3 was not started.
