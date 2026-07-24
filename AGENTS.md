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

## Trading Safety Rules

- Never introduce live-trading support.
- Paper trading must remain the only permitted execution mode.
- Paper trading must default to enabled.
- Any attempt to disable paper-trading mode must raise `RuntimeError`.
- Never permit short selling in Version 1.
- Never permit leverage in Version 1.
- Never permit assets other than SPY in Version 1.
- Never let models bypass the risk engine.
- No model output may override risk limits.
- The prediction model must not communicate directly with a broker or execution adapter.
- Every proposed trade must pass through an independent risk-management layer.
- The application must fail safely by refusing to trade when required information is missing or uncertain.

## Data and Modeling Rules

- Never randomly shuffle financial time-series observations.
- All model evaluation must preserve chronological order.
- Never use centered rolling windows.
- Never use backward filling that introduces future information.
- Feature engineering must not use future observations.
- Never execute a signal on the candle that generated it.
- Signals calculated using one candle may execute no earlier than the next candle.
- Backtests must include configurable transaction costs and estimated slippage.
- Maintain explicit alignment between raw data, features, labels, predictions, signals, and fills.

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
