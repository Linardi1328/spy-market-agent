from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from typing import Any, cast

import pandas as pd
import pytest

from spy_market_agent.backtesting import (
    BacktestAccountingError,
    BacktestCostAssumptions,
    BacktestInputError,
    FillRecord,
    OrderCostEstimate,
    estimate_order_cost,
    maximum_affordable_buy_quantity,
)
from spy_market_agent.risk import BUY_SIDE, SELL_SIDE


def test_zero_cost_buy_and_sell_formulas() -> None:
    costs = BacktestCostAssumptions(
        commission_bps_per_side=Decimal("0"),
        slippage_bps_per_side=Decimal("0"),
    )

    buy = estimate_order_cost(
        side=BUY_SIDE,
        quantity=10,
        reference_open=Decimal("100"),
        cost_assumptions=costs,
    )
    sell = estimate_order_cost(
        side=SELL_SIDE,
        quantity=10,
        reference_open=Decimal("100"),
        cost_assumptions=costs,
    )

    assert buy.execution_price == Decimal("100")
    assert buy.execution_notional == Decimal("1000")
    assert buy.commission == Decimal("0")
    assert buy.cash_change == Decimal("-1000")
    assert sell.execution_price == Decimal("100")
    assert sell.cash_change == Decimal("1000")


def test_positive_commission_and_slippage_formulas() -> None:
    costs = BacktestCostAssumptions(
        commission_bps_per_side=Decimal("10"),
        slippage_bps_per_side=Decimal("20"),
    )

    buy = estimate_order_cost(
        side=BUY_SIDE,
        quantity=5,
        reference_open=Decimal("100"),
        cost_assumptions=costs,
    )
    sell = estimate_order_cost(
        side=SELL_SIDE,
        quantity=5,
        reference_open=Decimal("100"),
        cost_assumptions=costs,
    )

    assert buy.execution_price == Decimal("100.200")
    assert buy.execution_notional == Decimal("501.000")
    assert buy.commission == Decimal("0.501000")
    assert buy.slippage_cost == Decimal("1.000")
    assert buy.total_transaction_cost == Decimal("1.501000")
    assert buy.cash_change == Decimal("-501.501000")
    assert sell.execution_price == Decimal("99.800")
    assert sell.execution_notional == Decimal("499.000")
    assert sell.commission == Decimal("0.499000")
    assert sell.slippage_cost == Decimal("1.000")
    assert sell.cash_change == Decimal("498.501000")


def test_maximum_affordable_whole_share_quantity() -> None:
    costs = BacktestCostAssumptions(
        commission_bps_per_side=Decimal("10"),
        slippage_bps_per_side=Decimal("0"),
    )

    quantity = maximum_affordable_buy_quantity(
        available_cash=Decimal("1000"),
        reference_open=Decimal("100"),
        cost_assumptions=costs,
    )

    assert quantity == 9


@pytest.mark.parametrize(
    ("commission", "slippage"),
    [
        (Decimal("-1"), Decimal("0")),
        (Decimal("0"), Decimal("-1")),
        (True, Decimal("0")),
        (Decimal("NaN"), Decimal("0")),
        (Decimal("Infinity"), Decimal("0")),
    ],
)
def test_invalid_cost_assumptions_fail(commission: object, slippage: object) -> None:
    with pytest.raises(BacktestInputError):
        BacktestCostAssumptions(
            commission_bps_per_side=commission,  # type: ignore[arg-type]
            slippage_bps_per_side=slippage,  # type: ignore[arg-type]
        )


def test_sell_execution_price_must_remain_positive() -> None:
    costs = BacktestCostAssumptions(
        commission_bps_per_side=Decimal("0"),
        slippage_bps_per_side=Decimal("10000"),
    )

    with pytest.raises(BacktestAccountingError) as exc_info:
        estimate_order_cost(
            side=SELL_SIDE,
            quantity=1,
            reference_open=Decimal("100"),
            cost_assumptions=costs,
        )

    assert "non_positive_sell_execution_price" in exc_info.value.codes


def test_cost_assumptions_are_immutable() -> None:
    costs = BacktestCostAssumptions(
        commission_bps_per_side=Decimal("1"),
        slippage_bps_per_side=Decimal("2"),
    )

    with pytest.raises(FrozenInstanceError):
        costs.commission_bps_per_side = Decimal("0")  # type: ignore[misc]


def test_impossible_direct_order_cost_estimate_fails() -> None:
    with pytest.raises(BacktestAccountingError):
        OrderCostEstimate(
            side=BUY_SIDE,
            quantity=2,
            reference_open=Decimal("100"),
            execution_price=Decimal("101"),
            reference_notional=Decimal("999"),
            execution_notional=Decimal("202"),
            commission=Decimal("1"),
            slippage_cost=Decimal("2"),
            total_transaction_cost=Decimal("3"),
            cash_change=Decimal("-203"),
        )


def test_pandas_series_or_index_cost_sides_fail_structured() -> None:
    costs = BacktestCostAssumptions(
        commission_bps_per_side=Decimal("0"),
        slippage_bps_per_side=Decimal("0"),
    )
    with pytest.raises(BacktestInputError):
        estimate_order_cost(
            side=pd.Series([BUY_SIDE]),
            quantity=1,
            reference_open=Decimal("100"),
            cost_assumptions=costs,
        )
    with pytest.raises(BacktestInputError):
        OrderCostEstimate(
            side=pd.Index([BUY_SIDE]),
            quantity=1,
            reference_open=Decimal("100"),
            execution_price=Decimal("100"),
            reference_notional=Decimal("100"),
            execution_notional=Decimal("100"),
            commission=Decimal("0"),
            slippage_cost=Decimal("0"),
            total_transaction_cost=Decimal("0"),
            cash_change=Decimal("-100"),
        )


def test_fill_record_normalizes_numeric_string_money_values() -> None:
    raw = cast(Any, "100")
    raw_execution = cast(Any, "101")
    raw_reference_notional = cast(Any, "200")
    raw_execution_notional = cast(Any, "202")
    raw_one = cast(Any, "1")
    raw_two = cast(Any, "2")
    raw_three = cast(Any, "3")
    raw_cash_change = cast(Any, "-203")
    raw_cash_before = cast(Any, "1000")
    raw_cash_after = cast(Any, "797")
    fill = FillRecord(
        order_sequence_number=1,
        symbol="SPY",
        side=BUY_SIDE,
        quantity=2,
        signal_session=date(2024, 1, 2),
        execution_session=date(2024, 1, 3),
        reference_open=raw,
        execution_price=raw_execution,
        reference_notional=raw_reference_notional,
        execution_notional=raw_execution_notional,
        commission=raw_one,
        slippage_cost=raw_two,
        total_transaction_cost=raw_three,
        cash_change=raw_cash_change,
        shares_before=0,
        shares_after=2,
        cash_before=raw_cash_before,
        cash_after=raw_cash_after,
        risk_approved=True,
    )

    assert isinstance(fill.reference_open, Decimal)
    assert isinstance(fill.cash_after, Decimal)
