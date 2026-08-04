# Changelog

## [Unreleased]

No unreleased changes.

## [2.0.0-alpha.1] - 2026-08-05

Corresponding Python package version: `2.0.0a1`.

### Added

- Added the long-term future development roadmap and Version 2 phase/pre-release map.
- Added ignore rules for local smoke-test artifacts.
- Added the Version 2 Phase 1 real-SPY-data specification.
- Added explicit Alpaca historical SPY daily acquisition.
- Added separate market-data credentials.
- Added sanitized raw JSON storage.
- Added canonical validated CSV storage.
- Added XNYS session validation.
- Added deterministic manifests, SHA-256 checksums, and dataset identity.
- Added safe local storage and atomic multi-artifact rollback.
- Added deep offline dataset verification.
- Added synthetic offline fixtures and tests.
- Added provider, licensing, security, and reproducibility documentation.

### Verified

- 975 automated tests passed on the release-preparation branch.
- Branch-aware coverage was 85.20%, above the 85% gate.
- Owner-run Alpaca IEX smoke test acquired four SPY sessions for 2024-01-02 through
  2024-01-05.
- Deep verification passed for the owner-run smoke-test artifacts.
- Generated provider data remained outside Git.

### Limitations

- No real SPY dataset is distributed with the repository.
- Alpaca coverage is not proven back to SPY inception.
- SIP availability may depend on subscription.
- Corporate-action evidence remains limited to the documented provider adjustment policy.
- No model benchmark, accuracy result, or profitability claim is included.
- No real-time feed, shadow mode, or live-money execution is included.
- Version 2 Phase 2 has not begun.

## [1.0.0] - 2026-08-04

Version 1 is the completed educational and experimental SPY daily research,
risk-controlled backtesting, persistence, read-only presentation, and explicit paper-only
execution preparation release.

### Implemented

- Validated SPY-only daily OHLCV data contracts, XNYS session handling, deterministic
  checksums, and provider-independent market-data interfaces.
- Added leakage-safe trailing features and the Version 1 label: information through close
  of `t`, entry no earlier than open of `t + 1`, exit at open of `t + 6`, and a positive
  target only after estimated round-trip costs and slippage.
- Added chronological train, validation, and final-test model evaluation with gap-aware
  split contracts, deterministic logistic-regression and gradient-boosting candidates,
  validation-only selection, locked refit, and final-test diagnostics.
- Added a fixed long-or-cash strategy policy and risk-controlled backtesting with
  transaction costs, slippage, cash accounting, whole-share fills, equity curves, orders,
  risk decisions, metrics, and source-market lineage.
- Added SQLite persistence and audit replay for validated market data, model evaluations,
  backtest results, and local paper-execution ledger state.
- Added read-only FastAPI routes and a read-only Streamlit dashboard for persisted data
  status, model evaluations, backtests, risk state, and local paper-execution status.
- Added explicit Alpaca paper-only execution safeguards: broker-independent instruction
  and approval models, deterministic fingerprints, dual kill switches, paper endpoint
  verification, live-mode rejection, market-hours checks, execution-time risk evaluation,
  duplicate ID protection, same-symbol/session reservation, submission-unknown handling,
  and lookup-only reconciliation.
- Added quality and documentation work: full README rewrite, architecture,
  reproducibility, workflow, security/safety, demo, and portfolio documentation, plus
  documentation consistency tests.

### Limitations

- No committed real SPY dataset or market-data downloader exists.
- No live trading, live endpoint support, automatic order submission, scheduler, worker,
  deployment configuration, API write route, or dashboard execution control exists.
- No assets other than SPY, intraday data, short selling, leverage, margin, fractional
  shares, cancellation, replacement, stops, limits, brackets, OCO, or OTO are implemented.
- Backtests and classification metrics are diagnostics only and are not profitability,
  real-market accuracy, investment-advice, or real-money-readiness claims.
- Exact reproducibility can differ when dependency versions differ because no lock file is
  committed.

## Version 1 Development History

### Phase 1: Specification and Agent Instructions

- Created the project specification and permanent agent guardrails.
- Established the educational purpose, SPY-only scope, no-live-trading rule, chronological
  modeling rules, and phased development plan.

### Phase 2: Project Scaffold and Tooling

- Added the Python 3.12 `src` package layout, tests, placeholder data/artifact directories,
  `pyproject.toml`, `.env.example`, and initial README.
- Configured Pytest, pytest-cov, Ruff, and MyPy.

### Phase 3: Configuration, Data Schema, and Validation

- Added typed settings with safe execution defaults and secret-aware display values.
- Added provider-independent SPY daily market-data contracts, XNYS calendar support,
  deterministic checksums, and canonical OHLCV validation.
- Hardened validation, checksum, settings redaction, and calendar-boundary behavior through
  corrective passes recorded in `reviews/PHASE_03_REVIEW.md`.

### Phase 4: Feature Engineering and Chronological Splits

- Added leakage-safe trailing feature construction.
- Added the Version 1 open `t + 1` to open `t + 6` label definition.
- Added supervised dataset alignment and chronological split assignment.
- Hardened label, target, checksum, metadata, and split validation.

### Phase 5: Machine-Learning Baselines

- Added deterministic logistic-regression and gradient-boosting candidates.
- Added validation-only model selection, locked train-plus-validation refit, and final-test
  evaluation.
- Preserved fixed model lineage and hardened fitted-estimator validation.

### Phase 6: Strategy and Backtesting

- Added the fixed long-or-cash strategy policy and next-open execution mapping.
- Added independent SPY-only long-only risk evaluation.
- Added in-memory backtesting with transaction costs, slippage, portfolio accounting,
  execution-price lineage, and metrics.
- Hardened source-market provenance and replay validation.

### Phase 7: Persistence, API, and Dashboard

- Added explicit SQLite initialization and artifact repositories.
- Added persistence for validated market data, final model evaluations, and backtest results.
- Added read-only FastAPI routes and a read-only Streamlit dashboard.
- Hardened run IDs, pagination, persistence read paths, and JSON validation.

### Phase 8: Paper-Trading Preparation

- Added broker-independent paper-execution models, approvals, fingerprints, service, and
  durable SQLite ledger.
- Added an isolated Alpaca paper-only adapter.
- Added read-only API and dashboard paper-status views.
- Added dual kill switches, market-hours enforcement, refreshed broker-clock checks,
  unknown-submission handling, lookup-only reconciliation, and same-symbol/session
  reservation protection.

### Pre-Phase-9 Quality Correction

- Raised full-suite coverage above the 85% gate.
- Converted unexpected warnings into errors with exact documented upstream warning filters.
- Preserved logistic-regression semantic lineage as `classifier.penalty="l2"` while avoiding
  the scikit-learn explicit-penalty `FutureWarning`.

### Phase 9: Documentation, Polish, and Portfolio Readiness

- Rewrote the README to describe the completed Version 1 system and its limitations.
- Added architecture, reproducibility, workflow, safety, demo, and portfolio documentation.
- Added documentation consistency tests for files, links, route inventory, module paths, and
  paper-execution safety statements.
- Updated the project specification to mark Phase 9 documentation deliverables.
