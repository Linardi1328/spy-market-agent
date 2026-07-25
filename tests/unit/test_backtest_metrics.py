from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

import pandas as pd
import pytest

from spy_market_agent.backtesting import (
    FILL_COLUMNS,
    PORTFOLIO_COLUMNS,
    PROPOSED_ORDER_COLUMNS,
    RISK_DECISION_COLUMNS,
    BacktestMetricError,
    BacktestMetrics,
    calculate_backtest_metrics,
)


def portfolio_frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "session": [pd.Timestamp("2024-01-03").date(), pd.Timestamp("2024-01-04").date()],
            "signal_session": [
                pd.Timestamp("2024-01-02").date(),
                pd.Timestamp("2024-01-03").date(),
            ],
            "target_position": [1, 1],
            "cash": [100.0, 100.0],
            "shares": [99, 99],
            "close_price": [101.0, 102.0],
            "market_value": [9999.0, 10098.0],
            "equity": [10099.0, 10198.0],
            "daily_return": [0.0099, 10198.0 / 10099.0 - 1.0],
            "drawdown": [0.0, 0.0],
        },
        columns=list(PORTFOLIO_COLUMNS),
    )
    return frame


def fill_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_sequence_number": [1],
            "symbol": ["SPY"],
            "side": ["buy"],
            "quantity": [99],
            "signal_session": [pd.Timestamp("2024-01-02").date()],
            "execution_session": [pd.Timestamp("2024-01-03").date()],
            "reference_open": [100.0],
            "execution_price": [100.0],
            "reference_notional": [9900.0],
            "execution_notional": [9900.0],
            "commission": [0.0],
            "slippage_cost": [0.0],
            "total_transaction_cost": [0.0],
            "cash_change": [-9900.0],
            "shares_before": [0],
            "shares_after": [99],
            "cash_before": [10000.0],
            "cash_after": [100.0],
            "risk_approved": [True],
        },
        columns=list(FILL_COLUMNS),
    )


def proposed_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sequence_number": [1],
            "symbol": ["SPY"],
            "side": ["buy"],
            "quantity": [99],
            "signal_session": [pd.Timestamp("2024-01-02").date()],
            "execution_session": [pd.Timestamp("2024-01-03").date()],
            "target_position": [1],
            "reference_open": [100.0],
            "estimated_execution_price": [100.0],
            "estimated_commission": [0.0],
            "estimated_cash_change": [-9900.0],
            "current_cash": [10000.0],
            "current_shares": [0],
        },
        columns=list(PROPOSED_ORDER_COLUMNS),
    )


def decisions_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_sequence_number": [1],
            "approved": [True],
            "reason_codes": [("approved",)],
            "evaluated_session": [pd.Timestamp("2024-01-03").date()],
            "projected_cash": [100.0],
            "projected_shares": [99],
            "projected_market_value": [9900.0],
            "projected_equity": [10000.0],
        },
        columns=list(RISK_DECISION_COLUMNS),
    )


def with_bad_cell(frame: pd.DataFrame, column: str, value: object) -> pd.DataFrame:
    changed = frame.copy(deep=True)
    changed[column] = changed[column].astype("object")
    changed.at[0, column] = value
    return changed


def test_backtest_metrics_match_manual_example() -> None:
    metrics = calculate_backtest_metrics(
        portfolio_frame(),
        fill_frame(),
        proposed_frame(),
        decisions_frame(),
        initial_cash=Decimal("10000"),
    )

    assert metrics.session_count == 2
    assert metrics.final_cash == 100.0
    assert metrics.final_shares == 99
    assert metrics.final_market_value == 10098.0
    assert metrics.final_equity == 10198.0
    assert metrics.total_return == pytest.approx(0.0198)
    assert metrics.maximum_drawdown == 0.0
    assert metrics.total_reference_notional == 9900.0
    assert metrics.total_execution_notional == 9900.0
    assert metrics.total_commission == 0.0
    assert metrics.total_slippage_cost == 0.0
    assert metrics.total_transaction_cost == 0.0
    assert metrics.turnover_ratio == pytest.approx(9900.0 / ((10099.0 + 10198.0) / 2.0))
    assert metrics.exposure_fraction == 1.0
    assert metrics.proposed_order_count == 1
    assert metrics.approved_order_count == 1
    assert metrics.rejected_order_count == 0
    assert metrics.fill_count == 1


def test_zero_trade_metrics_are_valid() -> None:
    empty_fills = pd.DataFrame(columns=list(FILL_COLUMNS))
    empty_orders = pd.DataFrame(columns=list(PROPOSED_ORDER_COLUMNS))
    empty_decisions = pd.DataFrame(columns=list(RISK_DECISION_COLUMNS))
    portfolio = portfolio_frame()
    portfolio["shares"] = 0
    portfolio["market_value"] = 0.0
    portfolio["cash"] = 10000.0
    portfolio["equity"] = 10000.0
    portfolio["daily_return"] = 0.0
    portfolio["drawdown"] = 0.0

    metrics = calculate_backtest_metrics(
        portfolio,
        empty_fills,
        empty_orders,
        empty_decisions,
        initial_cash=Decimal("10000"),
    )

    assert metrics.fill_count == 0
    assert metrics.turnover_ratio == 0.0
    assert metrics.exposure_fraction == 0.0


def test_invalid_metric_count_relationships_and_nonfinite_values_fail() -> None:
    with pytest.raises(BacktestMetricError):
        BacktestMetrics(
            session_count=1,
            initial_cash=10000.0,
            final_cash=10000.0,
            final_shares=0,
            final_market_value=0.0,
            final_equity=10000.0,
            total_return=0.0,
            maximum_drawdown=0.0,
            total_reference_notional=0.0,
            total_execution_notional=0.0,
            total_commission=0.0,
            total_slippage_cost=0.0,
            total_transaction_cost=0.0,
            turnover_ratio=0.0,
            exposure_fraction=0.0,
            proposed_order_count=1,
            approved_order_count=1,
            rejected_order_count=1,
            fill_count=1,
            buy_fill_count=1,
            sell_fill_count=0,
        )
    with pytest.raises(BacktestMetricError):
        calculate_backtest_metrics(
            portfolio_frame().assign(equity=float("inf")),
            fill_frame(),
            proposed_frame(),
            decisions_frame(),
            initial_cash=Decimal("10000"),
        )


@pytest.mark.parametrize(
    ("frame_name", "column", "bad_value"),
    [
        ("portfolio", "shares", "99"),
        ("portfolio", "drawdown", "0"),
        ("portfolio", "cash", None),
        ("portfolio", "equity", float("nan")),
        ("portfolio", "close_price", float("inf")),
        ("portfolio", "target_position", pd.Series([1])),
        ("proposed", "side", pd.Series(["buy"])),
        ("proposed", "symbol", pd.Index(["SPY"])),
        ("proposed", "quantity", [99]),
        ("fills", "side", pd.Index(["buy"])),
        ("fills", "commission", float("inf")),
        ("fills", "reference_open", None),
        ("decisions", "approved", "yes"),
        ("decisions", "reason_codes", ["approved"]),
        ("decisions", "projected_cash", pd.Series([100.0])),
    ],
)
def test_metric_frames_reject_malformed_public_values(
    frame_name: str,
    column: str,
    bad_value: object,
) -> None:
    portfolio = portfolio_frame()
    fills = fill_frame()
    proposed = proposed_frame()
    decisions = decisions_frame()
    if frame_name == "portfolio":
        portfolio = with_bad_cell(portfolio, column, bad_value)
    elif frame_name == "fills":
        fills = with_bad_cell(fills, column, bad_value)
    elif frame_name == "proposed":
        proposed = with_bad_cell(proposed, column, bad_value)
    else:
        decisions = with_bad_cell(decisions, column, bad_value)

    with pytest.raises(BacktestMetricError):
        calculate_backtest_metrics(
            portfolio,
            fills,
            proposed,
            decisions,
            initial_cash=Decimal("10000"),
        )


def test_direct_false_metric_identities_fail() -> None:
    base = calculate_backtest_metrics(
        portfolio_frame(),
        fill_frame(),
        proposed_frame(),
        decisions_frame(),
        initial_cash=Decimal("10000"),
    )

    with pytest.raises(BacktestMetricError):
        BacktestMetrics(
            **{**asdict(base), "total_return": base.total_return + 0.01},
        )
    with pytest.raises(BacktestMetricError):
        BacktestMetrics(
            **{**asdict(base), "initial_cash": 9999.0},
        )
    with pytest.raises(BacktestMetricError):
        BacktestMetrics(
            **{**asdict(base), "final_equity": base.final_equity + 1.0},
        )
    with pytest.raises(BacktestMetricError):
        BacktestMetrics(
            **{**asdict(base), "total_transaction_cost": base.total_transaction_cost + 1.0},
        )
