# Version 2 Phase 2 Benchmark Policy

Status: Implementation in review

This policy records the exact implementation decisions for the Version 2 Phase 2 Real
Historical Benchmark infrastructure. It is not an acceptance report and does not claim that a
real SPY benchmark has been run.

## Persistence

Phase 2 uses immutable file-based artifacts under `artifacts/benchmarks/<benchmark_id>/`.
SQLite schema changes are not part of Phase 2. Model binaries are not persisted; the selected
model is reconstructed from locked configuration and deterministically refit.

## Feed Policy

- Primary benchmark role requires Alpaca `sip`, symbol `SPY`, timeframe `1Day`, and
  adjustment mode `all`.
- `iex` is limited single-exchange coverage and may be used only for diagnostic benchmarks.
- `iex` cannot be accepted as the primary benchmark without an approved specification
  amendment.
- Feed evidence is owner-provided through `record-feed-decision`; the command makes no
  network request and stores no credentials, raw provider payload, or account identifier.

## Split Algorithm

Constants:

- `FEATURE_WARMUP_ROWS = 20`
- `ENTRY_OFFSET_SESSIONS = 1`
- `EXIT_OFFSET_SESSIONS = 6`
- `MANDATORY_GAP_SESSIONS = 5`
- `BOUNDARY_EXCLUSION_SESSIONS = 6`

After feature warm-up and label availability exclusions, let `U` be the ordered supervised
rows. The algorithm computes:

- `N = len(U)`
- `assignable_rows = N - (2 * BOUNDARY_EXCLUSION_SESSIONS)`
- `train_rows = floor(assignable_rows * 70 / 100)`
- `validation_rows = floor(assignable_rows * 15 / 100)`
- `final_test_rows = assignable_rows - train_rows - validation_rows`

The final test receives every rounding remainder. Boundaries are never moved for class
balance or model outcomes. Training must contain at least 756 rows with 120 positive and 120
negative labels. Validation and final test must each contain at least 252 rows with 40
positive and 40 negative labels.

## Model Candidates

Only the existing approved candidates are used:

- `logistic_regression`: `Pipeline(StandardScaler, LogisticRegression)`,
  `penalty=l2`, `C=1.0`, `solver=liblinear`, `max_iter=2000`, `class_weight=None`,
  `random_state=42`.
- `gradient_boosting`: `GradientBoostingClassifier`, `n_estimators=100`,
  `learning_rate=0.05`, `max_depth=2`, `min_samples_leaf=5`, `subsample=1.0`,
  `random_state=42`, `n_iter_no_change=None`.

Configurations are verified against `fixed_model_parameters(...)`.

## Selection Rule

Validation-only selection uses:

1. Higher validation ROC AUC.
2. Lower validation log loss.
3. Lower validation Brier score.
4. `logistic_regression` as the simpler-model tie-break.

Undefined ROC AUC fails closed for honest candidate selection.

## Baselines

Classification baselines:

- `majority_class`: majority derived from training only; training tie selects class `0`.
- `always_positive`: probability `1.0`, prediction `1`.
- `always_negative`: probability `0.0`, prediction `0`.
- `training_prevalence`: probability is training positive prevalence; diagnostic class uses
  fixed threshold `0.5`.

Strategy comparators:

- `always_cash`
- `buy_and_hold`
- `fixed_20_session_momentum`

Momentum is `adjusted_close_t / adjusted_close_t_minus_20_sessions - 1`; it is long when
momentum is greater than zero and cash otherwise. Lookback and threshold are not tunable.

## Cost Matrix

Initial cash is `Decimal("10000")`, annualized risk-free rate is `0.0`, cash yield is zero,
whole shares are required, and no intermediate cents quantization is applied.

| Scenario | Commission bps/side | Slippage bps/side |
| --- | ---: | ---: |
| `idealized` | `0` | `0` |
| `base` | `0.125` | `0.25` |
| `adverse` | `1` | `2` |
| `severe` | `10` | `20` |

`base` is the label and primary strategy scenario. Other scenarios are diagnostics using the
unchanged model and unchanged signals.

## Regime Definitions

Regimes are descriptive diagnostics only and are locked before validation.

- `trend_200`: arithmetic mean of the most recent 200 adjusted closes through session `t`;
  bull when `adjusted_close_t >= trailing_200_mean_t`, bear otherwise, unavailable with
  fewer than 200 closes.
- `realized_volatility_20`: sample standard deviation (`ddof=1`) of the most recent 20 daily
  log returns ending at session `t`, annualized with `sqrt(252)`. The high/lower threshold is
  the training-partition median valid value and is frozen in `benchmark_lock.json`.
- `drawdown_10`: running peak through session `t`; drawdown when
  `adjusted_close_t / running_peak_t - 1 <= -0.10`, normal otherwise.
- `calendar_year`: XNYS session calendar year, reported independently.

Regime cells with fewer than 40 observations are labelled `small_sample` and are not
interpreted.

## Artifact Schemas

Benchmark artifact schema version: `spy-v2-phase2-benchmark-artifacts-v1`.

Expected generated artifacts include `benchmark_lock.json`, `benchmark_lock.sha256`,
`feed_availability.json`, `dataset_eligibility.json`, `split_manifest.json`,
`validation_results.json`, `classification_baselines.json`, `strategy_baselines.json`,
`selected_model_manifest.json`, `final_test_readiness.json`, `final_test_lock.json`,
`final_test_access.json`, `final_test_results.json`, `cost_sensitivity.json`,
`regime_results.json`, `backtest_results.json`, `artifact_index.json`, and
`benchmark_report.md`. Not every artifact exists at every stage.

JSON artifacts are deterministic UTF-8 with sorted keys, compact separators, no
NaN/Infinity, LF newline, terminal newline, ISO dates/timestamps, deterministic Decimal
serialization, benchmark ID, dataset ID, schema version, and checksum coverage.

## Final-Test Access Policy

Before final-test acknowledgement, final metrics, final strategy results, final cost
sensitivity, and final regime diagnostics are unavailable. `run-final-test` writes
`final_test_access.json` before loading final-test labels. A completed non-audit final run is
not silently repeated; audit replay can only verify an existing completed result.

## Limitations

Phase 2 infrastructure measures historical evidence. It does not add new models, features,
hyperparameter search, calibration, threshold tuning, paper-execution behavior, API write
routes, dashboard execution controls, real-time data, live-money support, or assets other
than SPY. No profitability or investment recommendation is produced.
