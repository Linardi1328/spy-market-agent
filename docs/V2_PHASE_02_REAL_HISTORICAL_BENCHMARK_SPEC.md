# Version 2 Phase 2 — Real Historical Benchmark Specification

Status: Planning — awaiting review and implementation approval

Target future release: `v2.0.0-alpha.2`

Future Python package version: `2.0.0a2`

Planned implementation branch: `review/v2-phase-02-real-benchmark`

This specification does not authorize implementation until it is reviewed and explicitly
approved. Phase 2 evaluates the existing approved research pipeline using frozen real
historical SPY data. It does not authorize new model research, live execution, shadow
operation, additional paper-execution behavior, profitability claims, or investment
suitability claims.

## Table of Contents

- [1. Purpose](#1-purpose)
- [2. Entry Criteria](#2-entry-criteria)
- [3. In Scope](#3-in-scope)
- [4. Explicitly Out of Scope](#4-explicitly-out-of-scope)
- [5. Dataset Eligibility Contract](#5-dataset-eligibility-contract)
- [6. Historical-Depth and Regime Requirements](#6-historical-depth-and-regime-requirements)
- [7. Benchmark Lock](#7-benchmark-lock)
- [8. Chronological Split Policy](#8-chronological-split-policy)
- [9. Final-Test Protection](#9-final-test-protection)
- [10. Existing Model Candidates](#10-existing-model-candidates)
- [11. Classification Baselines](#11-classification-baselines)
- [12. Strategy Baselines](#12-strategy-baselines)
- [13. Classification Metrics](#13-classification-metrics)
- [14. Backtest and Strategy Metrics](#14-backtest-and-strategy-metrics)
- [15. Cost and Slippage Scenarios](#15-cost-and-slippage-scenarios)
- [16. Regime Diagnostics](#16-regime-diagnostics)
- [17. Reproducibility and Lineage](#17-reproducibility-and-lineage)
- [18. Benchmark Artifacts](#18-benchmark-artifacts)
- [19. Persistence Decision](#19-persistence-decision)
- [20. Command-Line Workflow](#20-command-line-workflow)
- [21. Failure Handling](#21-failure-handling)
- [22. Security and Privacy](#22-security-and-privacy)
- [23. Testing Plan](#23-testing-plan)
- [24. Real Benchmark Acceptance Procedure](#24-real-benchmark-acceptance-procedure)
- [25. Acceptance Criteria](#25-acceptance-criteria)
- [26. Rejection Criteria](#26-rejection-criteria)
- [27. Deliverables for the Future Implementation](#27-deliverables-for-the-future-implementation)
- [28. Versioning Contract](#28-versioning-contract)
- [29. Approval Boundary](#29-approval-boundary)

## 1. Purpose

Phase 2 establishes the first reproducible real-data benchmark for the existing SPY research
system. Its purpose is evidence measurement, not model research.

The objective is to determine:

- how the existing Version 1 models behave on frozen real historical SPY data;
- whether the results exceed simple naive classification and strategy baselines;
- how strategy results change under realistic transaction-cost and slippage assumptions;
- how classification and strategy diagnostics differ across major market regimes;
- whether the current system has enough evidence to justify Version 2 Phase 3 research.

Phase 2 does not guarantee profitability, real-market accuracy, investment suitability, or
live-money readiness. A weak benchmark result is valid evidence and must be reported
honestly.

## 2. Entry Criteria

Phase 2 implementation may begin only after all of the following are true:

- Version 2 Phase 1 is released as `v2.0.0-alpha.1`.
- Real historical acquisition and deep offline verification have passed.
- A canonical dataset manifest and SHA-256 checksums exist locally.
- The dataset is legal for the owner's approved local research use.
- No restricted raw or canonical provider dataset is committed to Git.
- The dataset provider, feed, adjustment mode, and date range are explicit.
- Package/runtime version begins at `2.0.0a1`.
- All Phase 1 verification gates pass before implementation starts.

## 3. In Scope

Phase 2 may include:

- loading a verified Phase 1 canonical SPY dataset;
- dataset eligibility checks;
- dataset and benchmark lock records;
- fixed chronological train, validation, and final-test periods;
- gap-aware splits;
- existing Version 1 features and labels;
- existing deterministic model candidates;
- validation-only model selection;
- untouched final-test evaluation;
- naive classification baselines;
- naive strategy baselines;
- cost-aware and slippage-aware backtesting;
- regime-based diagnostic reporting;
- benchmark manifests and lineage;
- reproducible machine-readable results;
- human-readable benchmark reports;
- offline synthetic tests;
- owner-run real-data benchmark acceptance.

## 4. Explicitly Out of Scope

Phase 2 does not authorize:

- new features;
- feature selection research;
- hyperparameter optimization;
- probability calibration;
- threshold optimization;
- new model families;
- deep learning;
- alternative labels or forecast horizons;
- walk-forward research beyond the existing approved split behavior;
- real-time feeds;
- shadow mode;
- new paper-execution behavior;
- live-money execution;
- assets other than SPY;
- portfolio optimization;
- automatic scheduling;
- cloud deployment;
- profitability guarantees.

These items belong to later phases or separate approval processes.

## 5. Dataset Eligibility Contract

The benchmark dataset must be accepted only when all of the following hold:

- symbol is exactly `SPY`;
- timeframe is exactly `1Day`;
- provider is recorded;
- feed is recorded;
- adjustment mode is recorded;
- one consistent adjusted OHLCV series is used throughout;
- raw and adjusted fields are never mixed;
- canonical schema version is supported;
- Phase 1 dataset manifest verification passes;
- canonical checksum matches;
- dataset identity matches;
- XNYS sessions validate;
- no duplicate sessions exist;
- no unexpected missing sessions exist;
- no incomplete current session exists;
- no future-dated session exists;
- numeric and OHLCV validation passes;
- the dataset meets the minimum historical-depth requirement.

The benchmark must consume the canonical dataset through the Phase 1 manifest and deep
verification flow. It must not accept an arbitrary CSV path that bypasses the manifest,
checksum, session, lineage, and schema checks.

## 6. Historical-Depth and Regime Requirements

Phase 2 must not assume that Alpaca access reaches SPY inception. Phase 1 provider review
recorded that broad historical coverage and subscription availability remain limitations for
future benchmarking.

A minimum acceptable benchmark dataset should include, where provider coverage permits:

- at least eight complete calendar years or an explicitly reviewed alternative;
- the 2020 pandemic crash and recovery;
- the 2022 inflation/rate-hike bear market;
- at least one lower-volatility expansion period;
- at least one high-volatility period;
- a recent completed period ending no later than the latest fully completed approved
  research year.

An owner-run availability probe is required before exact dates are locked. The final
implementation must create a dataset eligibility report containing:

- requested range;
- actual range;
- number of sessions;
- included regimes;
- important regimes not covered;
- provider/feed limitations;
- whether the minimum depth requirement passed.

When minimum coverage cannot be obtained, Phase 2 must fail closed. It must not silently
shorten the benchmark, claim completion, or proceed without an explicit specification
amendment or provider decision.

## 7. Benchmark Lock

Phase 2 requires an immutable benchmark lock document created before final-test access. The
planned path is:

```text
artifacts/benchmarks/<benchmark_id>/benchmark_lock.json
```

The lock must contain:

- benchmark ID;
- dataset ID;
- dataset manifest path reference;
- canonical checksum;
- provider;
- feed;
- adjustment mode;
- dataset range;
- feature-set identifier;
- label identifier;
- forecast horizon;
- split-policy identifier;
- exact train dates;
- exact validation dates;
- exact gap sessions;
- exact final-test dates;
- model candidate configurations;
- random seeds;
- signal-policy configuration;
- risk configuration;
- cost assumptions;
- slippage assumptions;
- baseline definitions;
- metric definitions;
- code commit SHA;
- package version;
- Python version;
- dependency versions;
- creation timestamp;
- owner acknowledgement;
- final-test lock status.

The benchmark ID must be deterministic from stable configuration and lineage inputs. It must
not be a random UUID alone. Any material change to dataset, schema, split dates, candidates,
costs, slippage, baseline definitions, metric definitions, or code lineage must create a new
benchmark identity.

## 8. Chronological Split Policy

Phase 2 must preserve all repository guardrails:

- never randomly shuffle observations;
- use chronological order;
- use at least five trading observations between train and validation;
- use at least five trading observations between validation and final test;
- ensure the five-day forward label cannot cross split boundaries;
- use features built only from information available through the close of day `t`;
- permit entry no earlier than open of `t + 1`;
- use exit at open of `t + 6`;
- keep future-return and target columns out of model features.

Exact split dates must be generated and recorded only after dataset eligibility is confirmed.
The deterministic default split policy is:

- training: earliest eligible sessions through approximately 70% of usable observations;
- validation: the next approximately 15%;
- final test: the final approximately 15%;
- mandatory gap sessions excluded between partitions;
- boundaries adjusted only to valid XNYS sessions;
- each partition must meet documented minimum positive and negative target counts;
- the final test must include at least one meaningful recent market regime where the
  eligible dataset permits it.

The Phase 2 implementation must not hard-code exact calendar dates before the owner-run
dataset availability probe. It must print and persist the exact resulting session dates.

## 9. Final-Test Protection

Phase 2 must use a two-stage benchmark workflow.

Stage A — development evaluation:

- load and verify the dataset;
- build features and labels;
- establish train, validation, and gap partitions;
- evaluate model candidates on validation only;
- compare validation metrics and naive baselines;
- lock the selected model and all configurations;
- generate a final-test readiness report;
- do not expose final-test model metrics.

Stage B — locked final evaluation:

- require an explicit owner acknowledgement flag;
- verify the benchmark lock has not changed;
- verify Git SHA, dataset checksum, and configurations;
- refit only using the approved locked process;
- evaluate the final test exactly once per benchmark identity;
- persist an immutable final-test access record;
- refuse accidental repeated final evaluation unless an explicit audit/replay mode proves no
  configuration changed;
- never tune based on final-test results.

Rerunning deterministic final evaluation for verification is allowed only as an audit replay.
Audit replay must not alter the model, configuration, split, or benchmark identity.

## 10. Existing Model Candidates

Phase 2 must use only the existing approved Version 1 model candidates:

- Logistic-regression baseline:
  - model name: `logistic_regression`;
  - estimator: `Pipeline`;
  - scaler: `StandardScaler`;
  - classifier: `LogisticRegression`;
  - `classifier.penalty`: `l2` semantic lineage, recorded by
    `fixed_model_parameters(...)`; the constructor may rely on the scikit-learn default
    rather than passing an explicit deprecated default;
  - `classifier.C`: `1.0`;
  - `classifier.solver`: `liblinear`;
  - `classifier.max_iter`: `2000`;
  - `classifier.class_weight`: `None`;
  - `classifier.random_state`: approved deterministic random seed.

- Gradient-boosting baseline:
  - model name: `gradient_boosting`;
  - estimator: `GradientBoostingClassifier`;
  - `n_estimators`: `100`;
  - `learning_rate`: `0.05`;
  - `max_depth`: `2`;
  - `min_samples_leaf`: `5`;
  - `subsample`: `1.0`;
  - `random_state`: approved deterministic random seed;
  - `n_iter_no_change`: `None`.

The default existing training configuration uses random seed `42`. Candidate parameters must
match the snapshots returned by `fixed_model_parameters(...)`.

Model selection must use validation evidence only. The current locked-selection tie-break
uses validation ROC AUC first, then lower validation log loss, then lower validation Brier
score, then `logistic_regression` as the simpler-baseline tie-break.

Phase 2 does not authorize new hyperparameters, grid search, random search, Bayesian
optimization, new estimators, probability calibration, or threshold research.

## 11. Classification Baselines

Phase 2 must include reproducible classification baselines:

- Majority-class prediction:
  - derive the majority class from training data only;
  - set `probability_positive` to `1.0` when the training majority class is positive and
    `0.0` when the training majority class is negative;
  - predict that class for validation and final partitions;
  - break training ties by choosing class `0` unless a future approved amendment changes the
    rule.

- Always-positive prediction:
  - set `probability_positive` to `1.0`;
  - always predict target `1`;
  - report that it is a naive diagnostic, not a strategy recommendation.

- Always-negative prediction:
  - set `probability_positive` to `0.0`;
  - always predict target `0`;
  - report that it is a naive diagnostic, not a strategy recommendation.

- Training-prevalence probability baseline:
  - compute positive-class prevalence from training data only;
  - emit that fixed probability for validation and final partitions;
  - convert probabilities to class labels using the documented diagnostic threshold.

Baselines must not use validation or final-test prevalence to define probabilities or class
predictions.

## 12. Strategy Baselines

Phase 2 must define strategy comparators clearly and avoid misleading comparisons.

Required comparators:

- Always-cash baseline:
  - no market exposure;
  - no transaction costs;
  - zero market return before any explicitly documented cash yield;
  - default cash yield remains zero unless separately specified.

- Buy-and-hold SPY baseline:
  - enter at the first eligible execution price;
  - hold through the final eligible exit;
  - include documented entry and exit costs;
  - use the same canonical adjusted series.

- Fixed existing signal-policy baseline:
  - apply the existing approved long-or-cash policy without model research;
  - use the current `STRATEGY_LONG_PROBABILITY_THRESHOLD` value of `0.5`;
  - keep model probabilities and risk checks aligned with existing Version 1 semantics.

- Optional simple trailing-momentum comparator:
  - use the canonical adjusted close series only;
  - compute `close_t / close_t_minus_20_sessions - 1.0` from trailing observations available
    through session `t`;
  - target long when the trailing 20-session momentum is strictly greater than `0.0`;
  - target cash otherwise;
  - execute no earlier than the next validated session open;
  - exclude rows that lack the 20-session trailing lookback;
  - must not become a tunable research model;
  - must not use validation or final-test results to choose lookback lengths, thresholds,
    exits, or inclusion.

Buy-and-hold must not be called equivalent to the model's overlapping five-day trade logic.
Reports must explain differences in exposure, holding periods, turnover, and cost treatment.

## 13. Classification Metrics

Phase 2 must report at least:

- accuracy;
- balanced accuracy;
- precision;
- recall;
- F1 score;
- confusion matrix;
- ROC AUC where both classes exist;
- PR AUC / average precision where both classes exist;
- log loss;
- Brier score;
- positive-class prevalence;
- predicted-positive rate.

Metric implementations must:

- use explicit positive-class semantics;
- handle one-class partitions safely;
- never silently replace undefined metrics with misleading values;
- record when a metric is undefined;
- avoid using final-test metrics for selection.

Accuracy alone is insufficient and must not be used as a standalone acceptance criterion.

## 14. Backtest and Strategy Metrics

Phase 2 must report at least:

- initial cash;
- final equity;
- total return;
- annualized return where mathematically valid;
- annualized volatility where valid;
- maximum drawdown;
- Sharpe ratio with an explicit documented risk-free-rate assumption;
- exposure percentage;
- turnover;
- number of orders;
- number of fills;
- number of completed trades;
- win rate where defined;
- average completed-trade return where defined;
- gross profit/loss;
- total transaction costs;
- total estimated slippage;
- rejected risk decisions;
- ending cash;
- ending shares.

All metrics must have documented formulas and undefined-value behavior. Rejected trades and
risk decisions must remain visible in reports and machine-readable artifacts.

## 15. Cost and Slippage Scenarios

Phase 2 must define a fixed cost/slippage scenario matrix before final-test evaluation.
Scenarios must apply to the selected model strategy and relevant strategy baselines.

Minimum scenario matrix:

- Idealized diagnostic:
  - zero commissions;
  - zero slippage;
  - clearly labelled unrealistic.

- Base scenario:
  - current approved Version 1 assumptions where a run configuration defines them;
  - if the repository has no single global numeric default, exact base values must be
    defined during Phase 2 implementation review before any benchmark execution.

- Adverse scenario:
  - meaningfully higher cost and slippage than the base scenario.

- Severe sensitivity scenario:
  - a clearly conservative stress value.

Existing repository facts:

- `BacktestConfig.initial_cash` is fixed at `Decimal("10000")` for the approved Version 1
  backtest.
- `BacktestCostAssumptions` requires explicit `commission_bps_per_side` and
  `slippage_bps_per_side`.
- Existing tests exercise zero-cost diagnostics and nonzero examples, but those examples do
  not constitute a globally approved real-data benchmark scenario matrix.

The future implementation must persist the exact numeric commission and slippage basis-point
values for every non-idealized scenario in `benchmark_lock.json` before any validation or
final-test benchmark run. If exact values are absent, Phase 2 must fail closed.

Cost and slippage assumptions must not be chosen after seeing final-test results.

## 16. Regime Diagnostics

Phase 2 must use a deterministic, descriptive regime taxonomy based only on market
observations and fixed rules, not on future model performance.

Potential diagnostics may include:

- bull versus bear periods using a fixed trailing-market rule;
- high versus lower volatility using a threshold learned from training data only or a fixed
  predefined value;
- drawdown periods;
- calendar subperiods;
- named historically documented periods.

Leakage controls:

- any learned regime threshold must be fitted on training data only;
- final-test regime labels must not use future information;
- named period boundaries must be fixed before evaluation.

Reports must include metric sample sizes for every regime and must not over-interpret small
regime samples.

## 17. Reproducibility and Lineage

Every result must capture:

- dataset ID and checksum;
- benchmark ID;
- feature-set identifier;
- label identifier;
- split dates;
- gap sessions;
- model configuration;
- random seeds;
- signal configuration;
- risk configuration;
- cost scenario;
- code SHA;
- package/runtime version;
- Python version;
- dependency versions;
- execution timestamp;
- host-independent deterministic result identity where practical.

Machine-specific absolute paths and usernames must not form result identity.

## 18. Benchmark Artifacts

Phase 2 should use ignored generated artifacts under:

```text
artifacts/benchmarks/<benchmark_id>/
  benchmark_lock.json
  dataset_eligibility.json
  split_manifest.json
  validation_results.json
  selected_model_manifest.json
  final_test_access.json
  final_test_results.json
  baseline_results.json
  cost_sensitivity.json
  regime_results.json
  backtest_results.json
  benchmark_report.md
```

Generated real benchmark results must be ignored by default until a separate review
determines which summaries may legally and safely be published. Small synthetic
expected-result fixtures may be committed. The real provider dataset must never be
committed.

## 19. Persistence Decision

Phase 2 implementation must explicitly decide whether benchmark artifacts:

- remain file-based;
- reuse existing SQLite research persistence;
- use both with a clearly defined source of truth.

Phase 2 must not automatically change the SQLite schema. Any persistence schema change
requires:

- explicit specification authorization;
- migration plan;
- rollback plan;
- tests;
- schema-version review.

File-based immutable benchmark artifacts are preferred when they satisfy Phase 2.

## 20. Command-Line Workflow

Phase 2 should plan explicit commands such as:

```bash
python -m spy_market_agent.benchmark.cli prepare \
  --manifest <phase-1-manifest> \
  --artifact-root ./artifacts/benchmarks
```

```bash
python -m spy_market_agent.benchmark.cli validate \
  --benchmark-lock <benchmark-lock>
```

```bash
python -m spy_market_agent.benchmark.cli run-validation \
  --benchmark-lock <benchmark-lock>
```

```bash
python -m spy_market_agent.benchmark.cli finalize-lock \
  --benchmark-lock <benchmark-lock> \
  --acknowledge-final-test-policy
```

```bash
python -m spy_market_agent.benchmark.cli run-final-test \
  --benchmark-lock <benchmark-lock> \
  --acknowledge-final-test-access
```

```bash
python -m spy_market_agent.benchmark.cli verify \
  --benchmark-report <report-or-manifest>
```

These commands are planning examples only and are not implemented by this specification
branch.

Required command behavior for a future implementation:

- no network access;
- no credentials;
- no broker client;
- no automatic acquisition;
- no automatic paper execution;
- non-zero exit codes on controlled failures;
- concise output without leaking raw provider data.

## 21. Failure Handling

Phase 2 must define explicit failures for:

- missing dataset manifest;
- dataset verification failure;
- unsupported dataset schema;
- dataset too short;
- missing required regime;
- split overlap;
- insufficient gap;
- label leakage;
- feature leakage;
- one-class training partition;
- one-class validation partition where selection is impossible;
- insufficient final-test size;
- benchmark-lock mismatch;
- dataset checksum mismatch;
- code/configuration mismatch;
- final-test access before lock;
- duplicate incompatible final-test access;
- result checksum mismatch;
- invalid metric;
- non-finite result;
- artifact write failure.

Failures must be explicit and fail closed.

## 22. Security and Privacy

Phase 2 must require:

- no Alpaca credentials in benchmark commands, reports, artifacts, fixtures, logs, tests, or
  Git;
- no account identifiers;
- no authentication headers;
- no raw restricted provider response in benchmark reports;
- no arbitrary pickle loading;
- safe artifact paths;
- atomic writes;
- no network activity on import or during normal benchmark runs;
- no broker client construction;
- no order submission;
- no user-specific absolute paths in committed reports;
- redaction of sensitive environment values.

## 23. Testing Plan

Required unit tests:

- dataset eligibility;
- manifest verification integration;
- benchmark identity;
- split construction;
- gap enforcement;
- no overlap;
- label-boundary safety;
- final-test lock behavior;
- baseline calculations;
- metric calculations;
- undefined metrics;
- cost scenario definitions;
- regime labels;
- artifact serialization;
- atomic writes;
- checksum verification;
- safe paths;
- CLI argument validation;
- no-network and no-broker guarantees.

Required integration tests:

- synthetic Phase 1 manifest through benchmark preparation;
- train/validation flow without final-test access;
- validation-only selection;
- benchmark lock finalization;
- explicit final-test execution;
- deterministic audit replay;
- corrupted dataset rejection;
- changed configuration rejection;
- cost-sensitivity generation;
- regime-report generation;
- existing Version 1 and Phase 1 behavior remaining unchanged.

Normal tests must remain offline and deterministic.

## 24. Real Benchmark Acceptance Procedure

The owner-run real benchmark acceptance sequence is:

1. Acquire or reuse an eligible local Phase 1 SPY dataset.
2. Deep-verify the Phase 1 dataset.
3. Prepare the benchmark and dataset eligibility report.
4. Review and approve exact dataset and split dates.
5. Run training and validation only.
6. Review validation results and baseline definitions.
7. Freeze the benchmark lock.
8. Explicitly authorize final-test access.
9. Run the final test.
10. Verify all generated artifacts.
11. Confirm Git remains clean.
12. Record only non-sensitive summary evidence.
13. Decide whether Phase 2 passed, failed, or requires redesign.

Codex must never claim this owner-run benchmark passed unless it was actually executed.

## 25. Acceptance Criteria

Phase 2 implementation may be approved only when:

- a verified real SPY dataset is used;
- dataset eligibility passes;
- dataset and benchmark IDs are deterministic;
- exact split dates are frozen;
- required gaps are enforced;
- no leakage is detected;
- existing Version 1 models are used without unapproved tuning;
- naive classification baselines are implemented;
- naive strategy baselines are implemented;
- validation-only selection is enforced;
- final-test access is explicit and recorded;
- cost/slippage scenarios are predefined;
- regime diagnostics are reproducible;
- classification and strategy reports are complete;
- results are reproducible offline from the local canonical dataset;
- no raw or canonical provider dataset is committed;
- no credential or account identifier is committed;
- existing tests continue to pass;
- coverage remains at least 85%;
- Ruff, formatting, and MyPy pass;
- no paper or live execution behavior changes;
- no profitability guarantee is made;
- Phase 3 has not begun.

## 26. Rejection Criteria

Phase 2 must be rejected or held when:

- historical coverage is insufficient;
- dataset verification fails;
- split leakage is found;
- final test was accessed before lock;
- configurations were changed after final-test review;
- baselines are missing or incorrectly constructed;
- results cannot be reproduced;
- metrics are non-finite or misleadingly substituted;
- costs are selected after viewing final results;
- real market data or secrets are committed;
- existing safety behavior regresses;
- the report makes unsupported profitability or live-readiness claims.

A weak benchmark result is not itself an engineering failure. The result must be reported
honestly even when the models underperform naive baselines.

## 27. Deliverables for the Future Implementation

Planned implementation deliverables include:

- benchmark domain models;
- dataset eligibility service;
- split-lock service;
- benchmark identity and manifest;
- baseline evaluators;
- classification metrics;
- strategy comparison service;
- cost-sensitivity service;
- regime diagnostics;
- final-test lock and access record;
- explicit benchmark CLI;
- immutable benchmark artifacts;
- offline synthetic fixtures;
- unit and integration tests;
- Phase 2 review report;
- data card;
- benchmark report;
- model comparison report;
- release notes and checklist for `2.0.0a2`.

Do not implement these deliverables in this specification branch.

## 28. Versioning Contract

- This specification branch remains package/runtime version `2.0.0a1`.
- The Phase 2 implementation branch begins at `2.0.0a1`.
- Phase 2 implementation must not bump the version at the start of implementation.
- After implementation, real benchmark acceptance, and all gates pass, the final
  release-preparation commit sets:
  - `pyproject.toml` package version to `2.0.0a2`;
  - `spy_market_agent.__version__` to `2.0.0a2`.
- Public Git release identifier: `v2.0.0-alpha.2`.
- The tag is created only after:
  1. specification approval;
  2. implementation approval;
  3. owner-run real benchmark acceptance;
  4. release-preparation merge;
  5. final verification on `main`.
- API, database, and dataset schema versions do not change merely because the package
  version changes.
- No tag is created when Phase 2 is incomplete or rejected.

## 29. Approval Boundary

This specification is planning documentation only. Version 2 Phase 2 implementation must not
begin until this document is reviewed and explicitly approved.
