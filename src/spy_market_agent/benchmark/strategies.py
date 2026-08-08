from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pandas as pd

from spy_market_agent.backtesting.costs import estimate_order_cost, maximum_affordable_buy_quantity
from spy_market_agent.backtesting.models import BUY_SIDE, SELL_SIDE, BacktestCostAssumptions
from spy_market_agent.benchmark.locks import CostScenario, StrategyMetricSet
from spy_market_agent.benchmark.metrics import strategy_metric_payload
from spy_market_agent.strategies.models import STRATEGY_LONG_PROBABILITY_THRESHOLD


def strategy_comparator_metrics(
    *,
    benchmark_id: str,
    dataset_id: str,
    market_data: pd.DataFrame,
    partition_labels: pd.DataFrame,
    probabilities: Sequence[float] | None,
    selected_model_name: str,
    cost_scenarios: Sequence[CostScenario],
    partition_name: str,
) -> dict[str, StrategyMetricSet]:
    results: dict[str, StrategyMetricSet] = {}
    signal_sessions = list(partition_labels["session"].to_list())
    for scenario in cost_scenarios:
        costs = BacktestCostAssumptions(
            commission_bps_per_side=scenario.commission_bps_per_side,
            slippage_bps_per_side=scenario.slippage_bps_per_side,
        )
        if probabilities is not None:
            model_targets = [
                1 if float(probability) >= STRATEGY_LONG_PROBABILITY_THRESHOLD else 0
                for probability in probabilities
            ]
            results[f"selected_model:{scenario.name}"] = _metric_set(
                benchmark_id=benchmark_id,
                dataset_id=dataset_id,
                strategy_name=f"selected_model_{selected_model_name}",
                partition_name=partition_name,
                cost_scenario=scenario.name,
                payload=_simulate_targets(
                    market_data=market_data,
                    signal_sessions=signal_sessions,
                    targets=model_targets,
                    costs=costs,
                ),
            )
        results[f"always_cash:{scenario.name}"] = _metric_set(
            benchmark_id=benchmark_id,
            dataset_id=dataset_id,
            strategy_name="always_cash",
            partition_name=partition_name,
            cost_scenario=scenario.name,
            payload=_always_cash_payload(row_count=len(partition_labels)),
        )
        results[f"buy_and_hold:{scenario.name}"] = _metric_set(
            benchmark_id=benchmark_id,
            dataset_id=dataset_id,
            strategy_name="buy_and_hold",
            partition_name=partition_name,
            cost_scenario=scenario.name,
            payload=_buy_and_hold_payload(
                market_data=market_data,
                entry_session=partition_labels.iloc[0]["entry_session"],
                exit_session=partition_labels.iloc[-1]["exit_session"],
                costs=costs,
            ),
        )
        momentum_targets = _momentum_targets(market_data, signal_sessions)
        results[f"fixed_20_session_momentum:{scenario.name}"] = _metric_set(
            benchmark_id=benchmark_id,
            dataset_id=dataset_id,
            strategy_name="fixed_20_session_momentum",
            partition_name=partition_name,
            cost_scenario=scenario.name,
            payload=_simulate_targets(
                market_data=market_data,
                signal_sessions=signal_sessions,
                targets=momentum_targets,
                costs=costs,
            ),
        )
    return results


def _metric_set(
    *,
    benchmark_id: str,
    dataset_id: str,
    strategy_name: str,
    partition_name: str,
    cost_scenario: str,
    payload: dict[str, Decimal | int | float | str | None],
) -> StrategyMetricSet:
    return StrategyMetricSet(
        benchmark_id=benchmark_id,
        dataset_id=dataset_id,
        strategy_name=strategy_name,
        partition_name=partition_name,
        cost_scenario=cost_scenario,
        metrics=payload,
    )


def _simulate_targets(
    *,
    market_data: pd.DataFrame,
    signal_sessions: Sequence[date],
    targets: Sequence[int],
    costs: BacktestCostAssumptions,
) -> dict[str, Decimal | int | float | str | None]:
    rows = market_data.set_index("session", drop=False)
    sessions = market_data["session"].to_list()
    index_by_session = {session: index for index, session in enumerate(sessions)}
    cash = Decimal("10000")
    shares = 0
    equity_curve: list[Decimal] = []
    exposure_flags: list[int] = []
    orders = fills = completed = rejected = 0
    gross_profit = Decimal("0")
    gross_loss = Decimal("0")
    transaction_costs = Decimal("0")
    estimated_slippage = Decimal("0")
    turnover = Decimal("0")
    entry_cash_change: Decimal | None = None
    completed_returns: list[Decimal] = []

    for signal_session, target in zip(signal_sessions, targets, strict=True):
        execution_index = index_by_session[signal_session] + 1
        execution_session = sessions[execution_index]
        row = rows.loc[execution_session]
        open_price = Decimal(str(row["open"]))
        close_price = Decimal(str(row["close"]))
        if target == 1 and shares == 0:
            orders += 1
            quantity = maximum_affordable_buy_quantity(
                available_cash=cash,
                reference_open=open_price,
                cost_assumptions=costs,
            )
            if quantity <= 0:
                rejected += 1
            else:
                fill = estimate_order_cost(
                    side=BUY_SIDE,
                    quantity=quantity,
                    reference_open=open_price,
                    cost_assumptions=costs,
                )
                cash += fill.cash_change
                shares += quantity
                fills += 1
                turnover += fill.reference_notional
                transaction_costs += fill.commission
                estimated_slippage += fill.slippage_cost
                entry_cash_change = fill.cash_change
        elif target == 0 and shares > 0:
            orders += 1
            fill = estimate_order_cost(
                side=SELL_SIDE,
                quantity=shares,
                reference_open=open_price,
                cost_assumptions=costs,
            )
            cash += fill.cash_change
            fills += 1
            completed += 1
            turnover += fill.reference_notional
            transaction_costs += fill.commission
            estimated_slippage += fill.slippage_cost
            if entry_cash_change is not None:
                trade_profit = fill.cash_change + entry_cash_change
                if trade_profit >= 0:
                    gross_profit += trade_profit
                else:
                    gross_loss += trade_profit
                completed_returns.append(trade_profit / abs(entry_cash_change))
            shares = 0
            entry_cash_change = None
        equity_curve.append(cash + Decimal(shares) * close_price)
        exposure_flags.append(1 if shares > 0 else 0)

    return _payload_from_curve(
        equity_curve=equity_curve,
        exposure_flags=exposure_flags,
        cash=cash,
        shares=shares,
        orders=orders,
        fills=fills,
        completed=completed,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        transaction_costs=transaction_costs,
        estimated_slippage=estimated_slippage,
        rejected=rejected,
        turnover=turnover,
        completed_returns=completed_returns,
    )


def _buy_and_hold_payload(
    *,
    market_data: pd.DataFrame,
    entry_session: date,
    exit_session: date,
    costs: BacktestCostAssumptions,
) -> dict[str, Decimal | int | float | str | None]:
    rows = market_data.set_index("session", drop=False)
    entry_open = Decimal(str(rows.loc[entry_session]["open"]))
    exit_open = Decimal(str(rows.loc[exit_session]["open"]))
    quantity = maximum_affordable_buy_quantity(
        available_cash=Decimal("10000"),
        reference_open=entry_open,
        cost_assumptions=costs,
    )
    if quantity <= 0:
        return _always_cash_payload(row_count=1)
    buy = estimate_order_cost(
        side=BUY_SIDE,
        quantity=quantity,
        reference_open=entry_open,
        cost_assumptions=costs,
    )
    sell = estimate_order_cost(
        side=SELL_SIDE,
        quantity=quantity,
        reference_open=exit_open,
        cost_assumptions=costs,
    )
    cash = Decimal("10000") + buy.cash_change + sell.cash_change
    trade_profit = buy.cash_change + sell.cash_change
    gross_profit = trade_profit if trade_profit >= 0 else Decimal("0")
    gross_loss = trade_profit if trade_profit < 0 else Decimal("0")
    return _payload_from_curve(
        equity_curve=[Decimal("10000") + buy.cash_change, cash],
        exposure_flags=[1, 0],
        cash=cash,
        shares=0,
        orders=2,
        fills=2,
        completed=1,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        transaction_costs=buy.commission + sell.commission,
        estimated_slippage=buy.slippage_cost + sell.slippage_cost,
        rejected=0,
        turnover=buy.reference_notional + sell.reference_notional,
        completed_returns=[trade_profit / abs(buy.cash_change)],
    )


def _always_cash_payload(*, row_count: int) -> dict[str, Decimal | int | float | str | None]:
    return _payload_from_curve(
        equity_curve=[Decimal("10000") for _ in range(max(row_count, 1))],
        exposure_flags=[0 for _ in range(max(row_count, 1))],
        cash=Decimal("10000"),
        shares=0,
        orders=0,
        fills=0,
        completed=0,
        gross_profit=Decimal("0"),
        gross_loss=Decimal("0"),
        transaction_costs=Decimal("0"),
        estimated_slippage=Decimal("0"),
        rejected=0,
        turnover=Decimal("0"),
        completed_returns=[],
    )


def _payload_from_curve(
    *,
    equity_curve: Sequence[Decimal],
    exposure_flags: Sequence[int],
    cash: Decimal,
    shares: int,
    orders: int,
    fills: int,
    completed: int,
    gross_profit: Decimal,
    gross_loss: Decimal,
    transaction_costs: Decimal,
    estimated_slippage: Decimal,
    rejected: int,
    turnover: Decimal,
    completed_returns: Sequence[Decimal],
) -> dict[str, Decimal | int | float | str | None]:
    wins = sum(1 for value in completed_returns if value > 0)
    win_rate = Decimal(wins) / Decimal(len(completed_returns)) if completed_returns else None
    average_return = (
        sum(completed_returns, Decimal("0")) / Decimal(len(completed_returns))
        if completed_returns
        else None
    )
    return strategy_metric_payload(
        initial_cash=Decimal("10000"),
        final_equity=equity_curve[-1],
        equity_curve=equity_curve,
        exposure_flags=exposure_flags,
        orders=orders,
        fills=fills,
        completed_trades=completed,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        transaction_costs=transaction_costs,
        estimated_slippage=estimated_slippage,
        rejected_risk_decisions=rejected,
        ending_cash=cash,
        ending_shares=shares,
        turnover=turnover,
        win_rate=win_rate,
        average_completed_trade_return=average_return,
    )


def _momentum_targets(market_data: pd.DataFrame, signal_sessions: Sequence[date]) -> list[int]:
    rows = market_data.reset_index(drop=True)
    index_by_session = {session: index for index, session in enumerate(rows["session"].to_list())}
    closes = rows["close"].astype("float64")
    targets: list[int] = []
    for session in signal_sessions:
        index = index_by_session[session]
        if index < 20:
            targets.append(0)
        else:
            momentum = closes.iloc[index] / closes.iloc[index - 20] - 1.0
            targets.append(1 if momentum > 0 else 0)
    return targets
