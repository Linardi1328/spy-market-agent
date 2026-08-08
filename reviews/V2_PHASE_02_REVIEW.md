# Version 2 Phase 2 Review

Status: Implementation in review

## Branch

- Starting main SHA: `a53160716ec9b266b9bee899a20855c24c4b7d91`
- Branch name: `review/v2-phase-02-real-benchmark`
- Final implementation SHA: to be reported after commit/push
- Package/runtime version: `2.0.0a1`
- Target public release identifier: `v2.0.0-alpha.2`
- Git tag status: `v2.0.0-alpha.2` not created

## Scope Implemented

Implemented a dedicated `spy_market_agent.benchmark` package for deterministic, auditable,
file-based Phase 2 benchmark infrastructure. The package accepts verified Phase 1 manifests,
records offline feed evidence, checks dataset eligibility, builds the approved features and
labels, constructs the Phase 2 chronological split, writes immutable benchmark locks, runs
validation-only model selection, creates final-test locks, gates final-test access, evaluates
locked baselines/strategies/costs/regimes, writes artifact indexes, and verifies artifact
checksums offline.

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
  `drawdown_10`, and independent `calendar_year` diagnostics.
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

## Controls

- Final-test row-level labels are guarded from Stage A services.
- `final_test_access.json` is written before final-test labels are loaded.
- A completed non-audit final run cannot be silently repeated.
- Audit replay verifies existing final artifacts and does not overwrite accepted results.
- Benchmark commands do not make network requests, require credentials, construct Alpaca
  clients, construct broker `TradingClient`, initialize execution databases, or submit
  orders.
- Safe path validation blocks path traversal, artifact-root escapes, source/test/doc/data/Git
  writes, symlink artifacts, and conflicting immutable writes.

## Tests

Test categories include Phase 1 manifest integration, dataset eligibility, feed rules,
split arithmetic, final-test label guards, model configuration snapshots, validation-only
selection, classification baselines, strategy comparators, cost matrix, Decimal accounting,
classification metrics, regimes, deterministic artifact serialization, locks, safe writes,
idempotency/conflict behavior, final-test lock/access, audit replay, corrupted artifact
verification, no-network/no-broker import safety, CLI behavior, documentation Quick Start
requirements, and existing Version 1/Phase 1 regression flows.

## Verification

- Full test total: `994` passing
- Unit-test total: `945` passing
- Integration-test total: `49` passing
- Targeted Phase 2 test total: `16` passing
- Coverage percentage: `85.21%`
- Ruff: passed
- Ruff format: passed
- MyPy: passed
- FutureWarning gate: passed
- Local startup smoke test: passed with temporary SQLite database, FastAPI
  `127.0.0.1:50237`, Streamlit `127.0.0.1:50238`, `/health` status `ok`,
  Streamlit HTTP response confirmed, no Alpaca/trading-client/order terms observed in
  startup logs, both child processes stopped, temporary database/logs removed

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
