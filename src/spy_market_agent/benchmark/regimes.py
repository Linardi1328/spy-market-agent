from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from spy_market_agent.benchmark.locks import RegimePolicy


@dataclass(frozen=True, slots=True)
class RegimeFrame:
    data: pd.DataFrame
    volatility_threshold: Decimal


def training_volatility_threshold(
    market_data: pd.DataFrame,
    *,
    training_sessions: Iterable[date],
) -> Decimal:
    labels = regime_frame(market_data, volatility_threshold=None)
    training_set = set(training_sessions)
    values = [
        Decimal(str(value))
        for value in labels.data.loc[
            labels.data["session"].isin(training_set), "realized_volatility_20_value"
        ].to_list()
        if pd.notna(value) and math.isfinite(float(value))
    ]
    if not values:
        return Decimal("0")
    values = sorted(values)
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return (values[midpoint - 1] + values[midpoint]) / Decimal("2")


def regime_frame(
    market_data: pd.DataFrame,
    *,
    volatility_threshold: Decimal | None,
) -> RegimeFrame:
    frame = market_data.loc[:, ["session", "close"]].copy(deep=True).reset_index(drop=True)
    close = frame["close"].astype("float64")
    trend_mean = close.rolling(window=200, min_periods=200, center=False).mean()
    log_returns = (close / close.shift(1)).map(math.log)
    realized_volatility = log_returns.rolling(window=20, min_periods=20, center=False).std(
        ddof=1
    ) * math.sqrt(252)
    running_peak = close.cummax()
    drawdown = close / running_peak - 1.0
    threshold = volatility_threshold
    if threshold is None:
        threshold = Decimal("0")
    threshold_float = float(threshold)
    frame["trend_200"] = [
        "unavailable" if pd.isna(mean) else ("bull" if price >= mean else "bear")
        for price, mean in zip(close.to_list(), trend_mean.to_list(), strict=True)
    ]
    frame["realized_volatility_20_value"] = realized_volatility.astype("float64")
    frame["realized_volatility_20"] = [
        (
            "unavailable"
            if pd.isna(value)
            else ("high_volatility" if float(value) > threshold_float else "lower_volatility")
        )
        for value in realized_volatility.to_list()
    ]
    frame["drawdown_10"] = ["drawdown" if float(value) <= -0.10 else "normal" for value in drawdown]
    frame["drawdown_10_value"] = drawdown.astype("float64")
    frame["calendar_year"] = [str(session.year) for session in frame["session"].to_list()]
    return RegimeFrame(data=frame, volatility_threshold=threshold)


def regime_policy_summary(policy: RegimePolicy) -> dict[str, object]:
    return {
        "trend_200": policy.trend_200,
        "realized_volatility_20": policy.realized_volatility_20,
        "drawdown_10": policy.drawdown_10,
        "calendar_year": policy.calendar_year,
        "volatility_threshold": policy.volatility_threshold,
        "small_sample_warning_threshold": policy.small_sample_warning_threshold,
    }


def regime_counts(
    *,
    labels: pd.DataFrame,
    regimes: pd.DataFrame,
    sessions: Iterable[date],
    small_sample_threshold: int = 40,
) -> dict[str, dict[str, dict[str, int | str]]]:
    session_set = set(sessions)
    target_by_session = labels.set_index("session")["target"].to_dict()
    joined = regimes[regimes["session"].isin(session_set)].copy(deep=True)
    result: dict[str, dict[str, dict[str, int | str]]] = {}
    for regime_name in ("trend_200", "realized_volatility_20", "drawdown_10", "calendar_year"):
        cells: dict[str, dict[str, int | str]] = {}
        for value, group in joined.groupby(regime_name, sort=True):
            targets = [int(target_by_session[session]) for session in group["session"].to_list()]
            positive = sum(targets)
            total = len(targets)
            warning = "small_sample" if total < small_sample_threshold else ""
            cells[str(value)] = {
                "sample_size": total,
                "positive_count": positive,
                "negative_count": total - positive,
                "warning": warning,
            }
        result[regime_name] = cells
    return result
