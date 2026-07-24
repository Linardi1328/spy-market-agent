# Risk-Controlled SPY Market Intelligence and Paper-Trading System

## Project Overview

This project is a portfolio-quality Python system for researching SPY market signals, evaluating machine-learning models, backtesting long-or-cash strategies, and later submitting simulated orders through a paper-trading account.

The system is educational and experimental. It must never claim, imply, or guarantee profitability. Its purpose is to demonstrate careful engineering, chronological market-data handling, model evaluation discipline, risk controls, and safe separation between research, decisioning, and execution.

## Problem Statement

Market-intelligence projects often fail by mixing research, prediction, backtesting, and execution in ways that introduce lookahead bias, unrealistic fills, uncontrolled risk, or unsafe broker access. This project addresses that problem by building a constrained, auditable workflow for SPY daily data:

1. Collect and validate daily OHLCV data.
2. Engineer features using only information available at the time.
3. Train and evaluate models with chronological splits.
4. Convert model outputs into proposed long-or-cash signals.
5. Backtest those signals with realistic execution timing, transaction costs, and slippage.
6. Pass all proposed trades through an independent risk-management layer.
7. In a later phase, submit only paper-trading orders after risk approval.

## Intended Users

- Developers evaluating a portfolio project that demonstrates Python, data engineering, machine learning, FastAPI, Streamlit, testing, and safety-aware trading-system design.
- Students or researchers learning about financial time-series modeling, backtesting constraints, and paper-trading workflows.
- The project owner, who will use the system as an educational research environment rather than an investment advisory tool.

This project is not intended for live-money trading, investment advice, or automated production trading.

## Project Objectives

- Build a clean, typed Python 3.12 codebase with small, testable modules.
- Restrict Version 1 to SPY, daily OHLCV data, and long-or-cash positions.
- Implement leakage-resistant feature engineering and chronological model evaluation.
- Establish logistic regression as the first baseline model.
- Add gradient boosting as a comparison model.
- Provide historical backtesting with configurable transaction costs and slippage.
- Enforce risk limits in a dedicated risk-management layer.
- Persist data and run metadata in SQLite.
- Expose research and backtest results through a FastAPI backend.
- Provide an interactive Streamlit dashboard.
- Prepare for Alpaca paper trading in a later phase while explicitly prohibiting live-money trading.
- Maintain a test suite with Pytest, formatting and linting with Ruff, and static type checking with MyPy.

## Version 1 Scope

- Python 3.12.
- SPY ETF only.
- Daily OHLCV market data.
- Long-or-cash positions only.
- No short selling.
- No leverage.
- Historical backtesting.
- Initial simulated capital of USD 10,000.
- Logistic regression as the first machine-learning baseline.
- Gradient boosting as a comparison model.
- FastAPI backend.
- Streamlit dashboard.
- SQLite database.
- Pytest test suite.
- Ruff linting and formatting.
- MyPy static type checking.
- Alpaca paper trading planned for a later development phase only.

## Explicit Non-Goals

- No live-money trading.
- No support for any asset other than SPY in Version 1.
- No intraday, tick, options, futures, crypto, or multi-asset data in Version 1.
- No short selling.
- No leverage or margin.
- No portfolio optimization across multiple instruments.
- No claims of profitability or investment suitability.
- No broker communication from prediction-model modules.
- No discretionary override that allows model outputs to bypass risk limits.
- No random train-test split for market data.
- No centered rolling-window features.
- No backward filling that introduces future information.
- No signal execution on the same candle that generated the signal.
- No hard-coded credentials or API keys.

## Proposed Architecture

The system should use a layered architecture with strict separation between research, decisioning, risk checks, execution, persistence, API, and dashboard concerns.

```text
Data Source
    |
    v
Market Data Ingestion
    |
    v
Data Validation
    |
    v
Feature Engineering
    |
    v
Strategy and Model Signal Generation
    |
    v
Risk Management
    |
    v
Backtesting Engine or Paper Execution Adapter
    |
    v
SQLite Persistence
    |
    +--> FastAPI Backend
    |
    +--> Streamlit Dashboard
    |
    v
Monitoring and Reports
```

Core design rules:

- Market data flows forward in chronological order.
- Feature engineering may only use observations available at or before the feature timestamp.
- A signal generated from candle `t` may execute no earlier than candle `t + 1`.
- Models produce predictions or scores only; they do not place orders.
- Strategies convert predictions into proposed trades only; they do not execute trades directly.
- Risk management independently validates every proposed trade.
- Execution modules can only execute risk-approved paper trades.
- Missing, stale, invalid, or uncertain required information must cause the system to refuse trading.

## Data Flow

1. Load configuration from environment variables and typed settings objects.
2. Ingest SPY daily OHLCV data from the configured source.
3. Validate schema, date order, missing values, duplicate timestamps, price sanity, and volume sanity.
4. Store validated raw data in SQLite.
5. Generate features from historical observations without lookahead leakage.
6. Generate labels for supervised learning, such as next-period return direction, while preserving chronological alignment.
7. Split data chronologically into train, validation, and test periods.
8. Train logistic regression and gradient boosting models.
9. Evaluate models using time-aware metrics and store results.
10. Convert model outputs into proposed long-or-cash signals.
11. Shift signals so execution occurs no earlier than the next candle.
12. Run proposed trades through risk management.
13. Backtest approved trades with initial capital, cash accounting, transaction costs, and slippage.
14. Persist backtest results, orders, positions, trades, metrics, and run metadata.
15. Serve results through FastAPI and Streamlit.
16. In a later phase, submit only risk-approved simulated orders to Alpaca paper trading.

## Module Responsibilities

### Configuration

- Load and validate runtime settings.
- Use environment variables for secrets and external service settings.
- Default paper trading to enabled.
- Raise `RuntimeError` for any attempt to disable paper-trading mode.
- Provide typed configuration objects.

### Market Data

- Fetch or load SPY daily OHLCV data.
- Normalize columns and timestamp handling.
- Ensure all data is explicitly tied to SPY in Version 1.
- Avoid embedding vendor-specific assumptions outside adapter modules.

### Data Validation

- Validate required columns: date, open, high, low, close, adjusted close when available, and volume.
- Validate chronological ordering.
- Detect duplicate dates.
- Detect impossible OHLC values, non-positive prices, and invalid volumes.
- Fail fast on missing data needed for modeling, backtesting, or trading decisions.

### Feature Engineering

- Compute time-series features using only present and past observations.
- Use trailing windows only.
- Avoid centered windows.
- Avoid backward filling that could introduce future information.
- Preserve feature-to-label alignment explicitly.
- Document each feature's economic or statistical intuition.

### Strategies

- Convert model predictions or rule-based signals into proposed long-or-cash target positions.
- Apply signal lagging so a signal generated from candle `t` executes no earlier than candle `t + 1`.
- Never submit trades directly to any broker or execution adapter.

### Machine-Learning Models

- Provide logistic regression as the first baseline.
- Provide gradient boosting as a comparison model.
- Train only on chronologically valid training data.
- Evaluate on later chronological periods.
- Never randomly shuffle financial time-series observations.
- Never communicate directly with broker or execution modules.

### Backtesting

- Simulate long-or-cash trading with initial capital of USD 10,000.
- Include configurable transaction costs.
- Include configurable estimated slippage.
- Account for cash, position size, fills, equity curve, drawdown, and turnover.
- Execute signals no earlier than the next candle after generation.
- Persist input parameters, assumptions, and results for reproducibility.

### Risk Management

- Independently evaluate every proposed trade before execution or backtesting.
- Enforce no short selling.
- Enforce no leverage.
- Enforce maximum position and available-cash constraints.
- Refuse trades when required price, cash, position, timestamp, or configuration information is missing or uncertain.
- Ensure no model output can override risk limits.

### Paper Execution

- Reserved for a later development phase.
- Support Alpaca paper trading only.
- Default paper trading to enabled.
- Raise `RuntimeError` if paper-trading mode is disabled.
- Refuse live-money endpoints, live account configuration, or any non-paper execution mode.
- Accept only risk-approved orders.

### Database Persistence

- Use SQLite for local persistence.
- Store market data, features metadata, model runs, evaluations, backtest runs, orders, trades, positions, equity curves, risk decisions, and configuration snapshots.
- Avoid storing secrets.
- Use migrations or explicit schema-management scripts once persistence is implemented.

### Monitoring

- Track data freshness, validation results, model-run metadata, backtest summaries, risk rejections, and paper-trading status.
- Avoid logging credentials.
- Prefer structured, redacted logs.

### FastAPI

- Expose read-oriented endpoints for data status, model results, backtest results, risk settings, and system health.
- Avoid placing training, backtesting, or broker logic directly in API route handlers.
- Require explicit service-layer calls for state-changing operations.

### Streamlit

- Provide an interactive dashboard for data quality, model evaluation, backtest results, risk settings, and paper-trading status.
- Present educational warnings and limitations.
- Never present outputs as financial advice or profitability guarantees.

### Automated Tests

- Cover configuration safety behavior, data validation, leakage-sensitive feature alignment, chronological splitting, signal lagging, backtest accounting, risk rejections, and API behavior.
- Tests must not be removed or weakened merely to obtain a passing build.

## Machine-Learning Objective

The initial supervised-learning task should be a binary classification problem:

- Predict whether SPY's next eligible return is positive after costs and execution assumptions, or alternatively whether the next-period close-to-close return is positive before costs if the distinction is clearly documented.
- Use features available at candle `t`.
- Generate predictions after candle `t` is complete.
- Permit execution no earlier than candle `t + 1`.

Model evaluation must preserve chronological order. Candidate metrics may include accuracy, precision, recall, F1, ROC AUC, calibration diagnostics, confusion matrix, directional hit rate, and strategy-level metrics from backtesting. Classification metrics must not be treated as evidence of profitability.

## Backtesting Requirements

- Use daily SPY OHLCV data only.
- Start with USD 10,000 simulated cash.
- Support long-or-cash positions only.
- Apply transaction costs on each trade.
- Apply configurable slippage assumptions.
- Use realistic execution timing: signals from candle `t` may execute no earlier than candle `t + 1`.
- Track cash, shares, market value, equity, returns, drawdown, orders, fills, and rejected trades.
- Ensure the backtest engine cannot enter short positions or use leverage.
- Keep backtest configuration and outputs reproducible.
- Report results with clear caveats and no profitability guarantees.

## Risk-Management Requirements

- Risk management must be independent from model and strategy modules.
- Every proposed trade must include enough information for risk validation.
- Required information should include symbol, side, target quantity or target weight, timestamp, estimated price, current cash, current position, and relevant risk configuration.
- Missing or uncertain required information must cause refusal to trade.
- Version 1 must reject:
  - Any symbol other than SPY.
  - Short positions.
  - Leverage.
  - Orders that exceed available simulated cash after costs and slippage.
  - Orders not produced through the approved signal and risk workflow.
  - Any attempt to bypass risk limits using model confidence or model score.

## Paper-Trading Restrictions

- Live-money trading must not be supported.
- Paper trading must default to enabled.
- Any attempt to disable paper-trading mode must raise `RuntimeError`.
- Alpaca integration is deferred to a later development phase.
- Paper execution adapters must never be imported by model modules.
- Paper execution must accept only risk-approved order instructions.
- Credentials must be read only from secure runtime configuration sources and never hard-coded.
- Credentials must never be logged, committed, or displayed in the dashboard.
- If account type, endpoint, credentials, clock, market status, order state, or risk approval cannot be verified, the system must refuse to trade.

## Testing Strategy

Use Pytest for automated tests, Ruff for linting and formatting, and MyPy for static type checking.

Test categories:

- Unit tests for configuration, validation, features, splitting, models, backtesting, risk, and persistence.
- Integration tests for end-to-end research and backtest flows using small fixture datasets.
- API tests for FastAPI endpoints.
- Dashboard smoke tests where practical.
- Regression tests for safety invariants.

Required safety tests:

- Disabling paper-trading mode raises `RuntimeError`.
- Live-trading configuration is rejected.
- Random train-test splitting is not used for market data.
- Feature rows do not use future observations.
- Centered rolling windows are not used.
- Backward filling does not introduce future information.
- Signals execute no earlier than the next candle.
- Short selling and leverage are rejected.
- Model output cannot bypass risk management.
- Missing required trade information causes refusal to trade.

## Security Requirements

- Never hard-code API keys, account IDs, secrets, or credentials.
- Never commit secrets.
- Never log credentials.
- Use environment variables or local secret-management mechanisms for sensitive settings.
- Provide `.env.example` style documentation later, with placeholder values only.
- Redact sensitive values in errors, logs, API responses, and dashboard views.
- Keep broker integration isolated from model and research modules.
- Fail safely when security-sensitive configuration is missing or inconsistent.

## Reproducibility Requirements

- Pin or lock dependencies once the project is scaffolded.
- Record Python version and tool versions.
- Persist model parameters, feature configuration, split dates, backtest settings, transaction cost assumptions, slippage assumptions, and run timestamps.
- Use deterministic random seeds where applicable.
- Preserve chronological data splits.
- Store enough metadata to reproduce a model evaluation or backtest run from the same input data.
- Document external data-source limitations, adjustment behavior, and refresh dates.

## Expected Repository Structure

No implementation files should be created during Phase 1. The proposed Version 1 structure is:

```text
spy-market-agent/
  PROJECT_SPEC.md
  AGENTS.md
  README.md
  pyproject.toml
  .env.example
  src/
    spy_market_agent/
      __init__.py
      config/
        __init__.py
        settings.py
      market_data/
        __init__.py
        providers.py
        schema.py
      validation/
        __init__.py
        market_data_checks.py
      features/
        __init__.py
        technical.py
        labels.py
      strategies/
        __init__.py
        signal_policy.py
      models/
        __init__.py
        baseline_logistic.py
        gradient_boosting.py
        evaluation.py
        splits.py
      backtesting/
        __init__.py
        engine.py
        costs.py
        metrics.py
      risk/
        __init__.py
        rules.py
        decisions.py
      execution/
        __init__.py
        paper.py
        alpaca_paper.py
      persistence/
        __init__.py
        database.py
        repositories.py
      monitoring/
        __init__.py
        logging.py
        health.py
      api/
        __init__.py
        main.py
        routes.py
        schemas.py
      dashboard/
        __init__.py
        streamlit_app.py
  tests/
    unit/
      test_config.py
      test_validation.py
      test_features.py
      test_splits.py
      test_backtesting.py
      test_risk.py
    integration/
      test_research_flow.py
      test_api.py
    fixtures/
      spy_daily_sample.csv
```

## Development Phases

### Phase 1: Specification and Agent Instructions

- Create `PROJECT_SPEC.md`.
- Create `AGENTS.md`.
- Do not create implementation files.
- Review and approve the architecture before scaffolding.

### Phase 2: Project Scaffold and Tooling

- Add package structure.
- Add `pyproject.toml`.
- Configure Python 3.12, Pytest, Ruff, and MyPy.
- Add initial README and `.env.example`.
- Add minimal import and tooling tests.

### Phase 3: Configuration, Data Schema, and Validation

- Implement typed settings.
- Enforce paper-trading safety defaults.
- Define SPY daily OHLCV schema.
- Add validation logic and fixture tests.

### Phase 4: Feature Engineering and Chronological Splits

- Implement leakage-safe trailing features.
- Implement label generation.
- Implement chronological train, validation, and test splitting.
- Add tests for alignment and leakage prevention.

### Phase 5: Machine-Learning Baselines

- Implement logistic regression baseline.
- Implement gradient boosting comparison.
- Add model evaluation and run metadata.
- Add tests using small deterministic datasets.

### Phase 6: Strategy and Backtesting

- Convert model outputs into long-or-cash target positions.
- Enforce next-candle execution.
- Implement transaction costs and slippage.
- Track portfolio accounting and metrics.
- Add risk-controlled backtest tests.

### Phase 7: Persistence, API, and Dashboard

- Add SQLite persistence.
- Add FastAPI read endpoints.
- Add Streamlit dashboard views.
- Add integration and smoke tests.

### Phase 8: Paper-Trading Preparation

- Add paper execution interfaces.
- Add Alpaca paper adapter only after explicit approval.
- Enforce paper-only endpoint restrictions.
- Add tests proving live trading cannot be configured.

### Phase 9: Documentation, Polish, and Portfolio Readiness

- Improve documentation.
- Add example workflows.
- Add reproducibility notes.
- Add screenshots or dashboard demo instructions.
- Review security and safety invariants.

## Definition of Done

Version 1 is done when:

- The project runs on Python 3.12.
- Pytest passes.
- Ruff passes.
- MyPy passes.
- SPY daily OHLCV data can be loaded, validated, and persisted.
- Features are generated without future leakage.
- Models are trained and evaluated with chronological splits.
- Logistic regression and gradient boosting results are available.
- Backtests run with USD 10,000 initial simulated capital.
- Transaction costs and slippage are configurable and applied.
- Signals execute no earlier than the next candle.
- Risk management approves or rejects every proposed trade.
- Short selling, leverage, non-SPY symbols, and live trading are rejected.
- FastAPI exposes core read endpoints.
- Streamlit displays data status, model evaluation, backtest results, and risk state.
- No credentials are committed, logged, or displayed.
- Documentation clearly states assumptions, limitations, and educational purpose.

## Known Risks and Limitations

- Historical backtests can overstate real-world performance because of data quality issues, survivorship assumptions, slippage assumptions, and unmodeled execution details.
- SPY-only daily data is intentionally narrow and may not generalize to other assets or timeframes.
- Logistic regression and gradient boosting can overfit noisy market data.
- Classification metrics may not translate into profitable or robust trading behavior.
- Transaction cost and slippage estimates are approximations.
- Data vendor adjustments, missing rows, and corporate-action handling must be understood and documented.
- Paper-trading fills may differ materially from live-market fills.
- API or dashboard results may be misinterpreted as advice unless educational warnings are visible.
- The project may require careful dependency management to keep the portfolio build reproducible.
- Any future broker integration increases security and safety complexity.
