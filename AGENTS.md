# Agent Instructions

These instructions are permanent guardrails for future Codex tasks in this repository.

## Required First Step

- Read `PROJECT_SPEC.md` before making changes.
- Treat `PROJECT_SPEC.md` as the source of truth for the agreed project scope, architecture, safety requirements, and development sequence.
- If a user request conflicts with `PROJECT_SPEC.md`, explain the conflict and ask for explicit approval before changing the architecture or scope.

## Engineering Standards

- Use Python 3.12.
- Use type hints for Python code.
- Prefer small, modular, reviewable changes.
- Keep implementation files aligned with the proposed package boundaries.
- Add or update tests for every feature.
- Run Pytest, Ruff, and MyPy after implementation changes.
- Clearly document assumptions and limitations.
- Ask for explicit approval before introducing a new major dependency.
- Ask for explicit approval before changing the agreed architecture.
- The market-data provider may remain undecided until Phase 3, but all market-data access must use a provider interface.

## Trading Safety Rules

- Never introduce live-trading support.
- Separate execution mode from execution permission.
- `EXECUTION_MODE` may only be `paper`.
- Any request for `live` execution must raise `RuntimeError`.
- `ENABLE_PAPER_EXECUTION` must default to `false`.
- `DRY_RUN` must default to `true`.
- Starting the application must not automatically submit paper orders.
- Paper-order submission must require deliberate configuration and explicit approval.
- Never permit short selling in Version 1.
- Never permit leverage in Version 1.
- Never permit assets other than SPY in Version 1.
- Never permit more than one open SPY position in Version 1.
- Never let models bypass the risk engine.
- No model output may override risk limits.
- The prediction model must not communicate directly with a broker or execution adapter.
- Every proposed trade must pass through an independent risk-management layer.
- The application must fail safely by refusing to trade when required information is missing or uncertain.
- Future paper execution must require unique signal identifiers and unique client-order identifiers.
- Future paper execution must reject duplicate orders and stale signals.
- Future paper execution must include a global kill switch.
- Future paper execution must verify broker account type and paper endpoint before order submission.

## Data and Modeling Rules

- Never randomly shuffle financial time-series observations.
- All model evaluation must preserve chronological order.
- Use a gap of at least five trading observations between training and validation and between validation and final testing.
- Apply the same minimum gap in time-series cross-validation.
- Keep the final test period untouched until feature selection, model selection, probability calibration, and signal-threshold selection are complete.
- Never use centered rolling windows.
- Never use backward filling that introduces future information.
- Feature engineering must not use future observations.
- The Version 1 target is: using information available through the close of trading day `t`, predict whether entering SPY at the open of `t + 1` and exiting at the open of `t + 6` produces a positive return after estimated round-trip transaction costs and slippage.
- Features may use data only through the close of day `t`.
- Prediction is generated after day `t` is complete.
- Entry may occur no earlier than the open of `t + 1`.
- Exit for the five-day target occurs at the open of `t + 6`.
- The target is `1` only when the executable return after estimated costs is greater than zero.
- Future return and target columns must never appear in model features.
- Backtests must include configurable transaction costs and estimated slippage.
- Maintain explicit alignment between raw data, features, labels, predictions, signals, and fills.
- Preserve the original vendor response as an immutable raw snapshot.
- Use one consistently adjusted OHLCV series for features, labels, backtesting, and benchmark calculations.
- Never mix raw and adjusted fields within one calculation.
- Record the adjustment policy in dataset and model metadata.
- Use the NYSE trading calendar and treat `America/New_York` as the market timezone.
- Store timestamps in UTC when full timestamps are required.
- Daily bars must correspond to valid exchange sessions.
- Weekends and exchange holidays must not be treated as missing observations.
- Reject duplicate trading-session dates.
- Exclude incomplete current-session candles.

## Data Lineage Rules

- Record data lineage and model-run metadata when available, including provider, download timestamp, symbol, timeframe, adjustment policy, first and last trading session, row count, dataset checksum, feature-schema version, label definition, Git commit hash, Python version, and dependency versions.

## Security Rules

- Never hard-code API keys, account IDs, secrets, or credentials.
- Never expose credentials in logs, test output, API responses, dashboard views, or committed files.
- Use environment variables or approved local secret-management mechanisms for credentials.
- Commit only placeholder examples for environment configuration.

## Testing Rules

- Do not remove tests merely to obtain a passing build.
- Do not weaken assertions merely to obtain a passing build.
- Add regression tests for safety-critical fixes.
- Prefer deterministic fixtures for market-data, feature, model, backtest, and risk tests.
- After implementation changes, run:

```bash
pytest
ruff check .
ruff format --check .
mypy .
```

If a command cannot be run, document the reason clearly in the final response.

## Documentation Rules

- Keep assumptions and limitations visible in user-facing documentation.
- Do not claim or imply profitability.
- Do not present model outputs, backtests, or dashboard results as investment advice.
- When adding or changing architecture, update `PROJECT_SPEC.md` after explicit approval.
