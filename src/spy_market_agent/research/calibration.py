from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd

from spy_market_agent.datasets.models import SupervisedDataset
from spy_market_agent.research.errors import ResearchRegistryError, raise_research_error
from spy_market_agent.research.models import CalibrationPolicy, CalibrationSplit, WalkForwardFold


def build_calibration_split(
    supervised: SupervisedDataset,
    *,
    fold: WalkForwardFold,
    policy: CalibrationPolicy,
) -> CalibrationSplit | None:
    if policy.method == "none":
        return None

    labels = supervised.labels.reset_index(drop=True)
    label_by_session = labels.set_index("session", drop=False)
    training_sessions = fold.training.prediction_sessions
    calibration_rows = policy.calibration_window_rows
    inner_gap = policy.inner_boundary_exclusion_rows
    estimator_training_count = len(training_sessions) - inner_gap - calibration_rows
    if estimator_training_count <= 0:
        raise_research_error(
            ResearchRegistryError,
            "insufficient_estimator_training_rows_for_calibration",
            "calibration split requires estimator rows before the inner boundary.",
        )

    estimator_sessions = training_sessions[:estimator_training_count]
    inner_boundary_sessions = training_sessions[
        estimator_training_count : estimator_training_count + inner_gap
    ]
    calibration_sessions = training_sessions[estimator_training_count + inner_gap :]
    if len(calibration_sessions) < policy.minimum_calibration_rows:
        raise_research_error(
            ResearchRegistryError,
            "insufficient_calibration_rows",
            "calibration rows do not meet the configured minimum.",
        )
    if policy.require_two_classes:
        _require_two_classes(label_by_session, estimator_sessions, scope_name="estimator_training")
        _require_two_classes(label_by_session, calibration_sessions, scope_name="calibration")
    if policy.method == "isotonic" and len(calibration_sessions) < policy.calibration_window_rows:
        raise_research_error(
            ResearchRegistryError,
            "insufficient_isotonic_calibration_rows",
            "isotonic calibration requires the full configured calibration window.",
        )
    return CalibrationSplit(
        fold_id=fold.fold_id,
        estimator_training_sessions=estimator_sessions,
        inner_boundary_excluded_sessions=inner_boundary_sessions,
        calibration_sessions=calibration_sessions,
        outer_boundary_excluded_sessions=fold.boundary_excluded_sessions,
    )


def _require_two_classes(
    label_by_session: pd.DataFrame,
    sessions: tuple[date, ...],
    *,
    scope_name: str,
) -> None:
    targets = [
        int(cast(int, label_by_session.loc[session, "target"]))
        for session in sessions
        if session in label_by_session.index
    ]
    if len(targets) != len(sessions) or set(targets) != {0, 1}:
        raise_research_error(
            ResearchRegistryError,
            f"{scope_name}_calibration_single_class",
            f"{scope_name} rows must contain both classes for calibration research.",
        )
