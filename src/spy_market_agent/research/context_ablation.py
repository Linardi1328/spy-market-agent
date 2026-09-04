from __future__ import annotations

import hashlib
import math
import statistics
import warnings
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import pairwise
from typing import Any, cast

import pandas as pd
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from spy_market_agent.features.models import FEATURE_SCHEMA_VERSION, FeatureSet
from spy_market_agent.intelligence.context_features import (
    MI2B_CONTEXT_FEATURE_POLICY_ID,
    MI2B_FEATURE_IDS,
    SPYContextFeatureBundle,
)
from spy_market_agent.intelligence.scenarios import ScenarioOutcome, ScenarioProbability
from spy_market_agent.research.scenario_candidate import (
    MI1D_CANDIDATE_ID,
    MI1D_FEATURE_COLUMNS,
    MI1D_FEATURE_POLICY_ID,
    MI1D_LOGISTIC_C,
    MI1D_LOGISTIC_MAX_ITER,
    MI1D_LOGISTIC_SOLVER,
    MI1D_LOGISTIC_TOL,
    ScenarioCandidateEvaluation,
    ScenarioCandidateFoldEvaluation,
    evaluate_development_multinomial_candidate,
)
from spy_market_agent.research.scenario_evaluation import (
    MI1C_POLICY_ID,
    ScenarioBaselineBenchmark,
    ScenarioEvaluationMetrics,
    calculate_scenario_probability_metrics,
)
from spy_market_agent.research.scenario_labels import ScenarioLabel, ScenarioLabelSet

MI2C_POLICY_ID = "mi2c-context-ablation-v1"
MI2C_CONTEXT_CANDIDATE_ID = "mi2c-context-multinomial-logistic-regression-v1"

MI2C_QQQ_IWM_FEATURE_IDS: tuple[str, ...] = MI2B_FEATURE_IDS[:8]
MI2C_VIX_FEATURE_IDS: tuple[str, ...] = MI2B_FEATURE_IDS[8:11]
MI2C_RATES_FEATURE_IDS: tuple[str, ...] = MI2B_FEATURE_IDS[11:14]


class ContextAblationVariant(StrEnum):
    SPY_ONLY = "SPY_ONLY"
    SPY_PLUS_QQQ_IWM = "SPY_PLUS_QQQ_IWM"
    SPY_PLUS_VIX = "SPY_PLUS_VIX"
    SPY_PLUS_RATES = "SPY_PLUS_RATES"
    SPY_PLUS_FULL_CONTEXT = "SPY_PLUS_FULL_CONTEXT"


@dataclass(frozen=True, slots=True)
class ContextAblationDefinition:
    variant: ContextAblationVariant
    context_feature_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.variant, ContextAblationVariant):
            raise ValueError("variant must be a ContextAblationVariant.")
        if len(set(self.context_feature_ids)) != len(self.context_feature_ids):
            raise ValueError("context_feature_ids must not contain duplicates.")
        if any(feature_id not in MI2B_FEATURE_IDS for feature_id in self.context_feature_ids):
            raise ValueError("context_feature_ids must come from the frozen MI-2B policy.")
        if self.variant == ContextAblationVariant.SPY_ONLY and self.context_feature_ids:
            raise ValueError("SPY_ONLY must not include context features.")
        if self.variant != ContextAblationVariant.SPY_ONLY and not self.context_feature_ids:
            raise ValueError("contextual variants must include context features.")

    @property
    def model_feature_columns(self) -> tuple[str, ...]:
        return (*MI1D_FEATURE_COLUMNS, *self.context_feature_ids)


MI2C_ABLATION_DEFINITIONS: tuple[ContextAblationDefinition, ...] = (
    ContextAblationDefinition(ContextAblationVariant.SPY_ONLY, ()),
    ContextAblationDefinition(ContextAblationVariant.SPY_PLUS_QQQ_IWM, MI2C_QQQ_IWM_FEATURE_IDS),
    ContextAblationDefinition(ContextAblationVariant.SPY_PLUS_VIX, MI2C_VIX_FEATURE_IDS),
    ContextAblationDefinition(ContextAblationVariant.SPY_PLUS_RATES, MI2C_RATES_FEATURE_IDS),
    ContextAblationDefinition(ContextAblationVariant.SPY_PLUS_FULL_CONTEXT, MI2B_FEATURE_IDS),
)
_DEFINITION_BY_VARIANT = {definition.variant: definition for definition in MI2C_ABLATION_DEFINITIONS}


@dataclass(frozen=True, slots=True)
class SPYContextFeatureHistory:
    source_market_data_checksum: str
    source_schema_version: str
    bundles: tuple[SPYContextFeatureBundle, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.source_market_data_checksum, field_name="source_market_data_checksum")
        if not self.source_schema_version.strip():
            raise ValueError("source_schema_version must not be empty.")
        if not self.bundles:
            raise ValueError("historical context bundles must not be empty.")
        anchors = tuple(bundle.anchor_session for bundle in self.bundles)
        if anchors != tuple(sorted(anchors)) or len(set(anchors)) != len(anchors):
            raise ValueError("historical context anchors must be unique and strictly increasing.")
        as_of_values = tuple(bundle.as_of for bundle in self.bundles)
        if as_of_values != tuple(sorted(as_of_values)) or len(set(as_of_values)) != len(
            as_of_values
        ):
            raise ValueError("historical context as_of values must be unique and strictly increasing.")
        if any(bundle.policy_id != MI2B_CONTEXT_FEATURE_POLICY_ID for bundle in self.bundles):
            raise ValueError("historical context must use the frozen MI-2B feature policy.")

    def bundle_for(self, anchor_session: date) -> SPYContextFeatureBundle:
        for bundle in self.bundles:
            if bundle.anchor_session == anchor_session:
                return bundle
        raise ValueError(f"missing MI-2B historical context for anchor {anchor_session.isoformat()}.")


@dataclass(frozen=True, slots=True)
class ContextAblationModelSnapshot:
    policy_id: str
    candidate_id: str
    variant: ContextAblationVariant
    feature_columns: tuple[str, ...]
    context_feature_policy_id: str
    feature_schema_version: str
    sklearn_version: str
    fit_row_count: int
    fit_first_anchor_session: date
    fit_last_anchor_session: date
    fit_last_outcome_session: date
    fit_context_digest: str
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    class_order: tuple[ScenarioOutcome, ...]
    coefficients: tuple[tuple[float, ...], ...]
    intercepts: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.policy_id != MI2C_POLICY_ID:
            raise ValueError("policy_id must match the frozen MI-2C policy.")
        if self.candidate_id != MI2C_CONTEXT_CANDIDATE_ID:
            raise ValueError("candidate_id must match the frozen MI-2C contextual candidate.")
        definition = _contextual_definition(self.variant)
        if self.feature_columns != definition.model_feature_columns:
            raise ValueError("feature_columns must match the frozen MI-2C ablation definition.")
        if self.context_feature_policy_id != MI2B_CONTEXT_FEATURE_POLICY_ID:
            raise ValueError("context_feature_policy_id must match the frozen MI-2B policy.")
        if self.feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise ValueError("feature_schema_version must match the existing feature schema.")
        if self.sklearn_version != sklearn.__version__:
            raise ValueError("sklearn_version must match the active scikit-learn runtime.")
        if self.fit_row_count <= 0:
            raise ValueError("fit_row_count must be positive.")
        if self.fit_first_anchor_session > self.fit_last_anchor_session:
            raise ValueError("fit anchor-session bounds are invalid.")
        if self.fit_last_outcome_session <= self.fit_last_anchor_session:
            raise ValueError("last fit outcome session must follow the last fit anchor session.")
        _require_sha256(self.fit_context_digest, field_name="fit_context_digest")
        feature_count = len(self.feature_columns)
        if len(self.scaler_mean) != feature_count:
            raise ValueError("scaler_mean must contain one value per model feature.")
        if len(self.scaler_scale) != feature_count:
            raise ValueError("scaler_scale must contain one value per model feature.")
        if any(not math.isfinite(value) for value in self.scaler_mean):
            raise ValueError("scaler_mean must contain only finite values.")
        if any(not math.isfinite(value) or value <= 0.0 for value in self.scaler_scale):
            raise ValueError("scaler_scale must contain only positive finite values.")
        if self.class_order != tuple(ScenarioOutcome):
            raise ValueError("class_order must match canonical ScenarioOutcome order.")
        if len(self.coefficients) != len(ScenarioOutcome):
            raise ValueError("coefficients must contain one row per scenario class.")
        if any(len(row) != feature_count for row in self.coefficients):
            raise ValueError("every coefficient row must contain one value per model feature.")
        if any(not math.isfinite(value) for row in self.coefficients for value in row):
            raise ValueError("coefficients must contain only finite values.")
        if len(self.intercepts) != len(ScenarioOutcome) or any(
            not math.isfinite(value) for value in self.intercepts
        ):
            raise ValueError("intercepts must contain one finite value per scenario class.")


@dataclass(frozen=True, slots=True)
class ContextAblationFoldEvaluation:
    baseline_fold_index: int
    model_snapshot: ContextAblationModelSnapshot
    assessment_anchor_sessions: tuple[date, ...]
    assessment_outcome_sessions: tuple[date, ...]
    assessment_outcomes: tuple[ScenarioOutcome, ...]
    probability_rows: tuple[tuple[ScenarioProbability, ...], ...]
    metrics: ScenarioEvaluationMetrics

    def __post_init__(self) -> None:
        if self.baseline_fold_index < 0:
            raise ValueError("baseline_fold_index must be non-negative.")
        row_count = len(self.assessment_anchor_sessions)
        if row_count == 0:
            raise ValueError("contextual assessment fold must not be empty.")
        if (
            len(self.assessment_outcome_sessions) != row_count
            or len(self.assessment_outcomes) != row_count
            or len(self.probability_rows) != row_count
            or self.metrics.row_count != row_count
        ):
            raise ValueError("contextual fold fields must have matching row counts.")
        if (
            self.assessment_anchor_sessions != tuple(sorted(self.assessment_anchor_sessions))
            or len(set(self.assessment_anchor_sessions)) != row_count
        ):
            raise ValueError("contextual assessment anchors must be unique and increasing.")
        if (
            self.assessment_outcome_sessions != tuple(sorted(self.assessment_outcome_sessions))
            or len(set(self.assessment_outcome_sessions)) != row_count
        ):
            raise ValueError("contextual assessment outcomes must be unique and increasing.")
        if self.model_snapshot.fit_last_outcome_session > self.assessment_anchor_sessions[0]:
            raise ValueError("contextual fit outcomes must be observable by assessment start.")
        for row in self.probability_rows:
            if tuple(item.outcome for item in row) != tuple(ScenarioOutcome):
                raise ValueError("contextual probabilities must use canonical scenario order.")
            if not math.isclose(
                sum(item.probability for item in row),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("contextual probability rows must sum to one.")

    @property
    def assessment_row_count(self) -> int:
        return len(self.assessment_anchor_sessions)


@dataclass(frozen=True, slots=True)
class ContextAblationVariantEvaluation:
    variant: ContextAblationVariant
    feature_columns: tuple[str, ...]
    horizon_length: int
    development_through_session: date
    source_market_data_checksum: str
    source_schema_version: str
    scenario_schema_id: str
    folds: tuple[ContextAblationFoldEvaluation, ...]
    pooled_metrics: ScenarioEvaluationMetrics
    median_fold_log_loss: float
    worst_fold_log_loss: float
    median_fold_brier_score: float
    worst_fold_brier_score: float

    def __post_init__(self) -> None:
        definition = _contextual_definition(self.variant)
        if self.feature_columns != definition.model_feature_columns:
            raise ValueError("variant feature_columns must match the frozen MI-2C definition.")
        if self.horizon_length not in {5, 20}:
            raise ValueError("horizon_length must be 5 or 20 sessions.")
        _require_sha256(self.source_market_data_checksum, field_name="source_market_data_checksum")
        if not self.source_schema_version.strip() or not self.scenario_schema_id.strip():
            raise ValueError("source and scenario schema identifiers must not be empty.")
        if not self.folds:
            raise ValueError("contextual evaluation must contain at least one fold.")
        fold_indexes = tuple(fold.baseline_fold_index for fold in self.folds)
        if fold_indexes != tuple(sorted(set(fold_indexes))):
            raise ValueError("contextual fold indexes must be unique and increasing.")
        if any(later != earlier + 1 for earlier, later in pairwise(fold_indexes)):
            raise ValueError("contextual fold indexes must be consecutive.")
        if any(fold.model_snapshot.variant != self.variant for fold in self.folds):
            raise ValueError("all contextual fold snapshots must match the evaluation variant.")
        if any(
            max(fold.assessment_outcome_sessions) > self.development_through_session
            for fold in self.folds
        ):
            raise ValueError("contextual assessment outcomes must not exceed development cutoff.")
        if sum(fold.assessment_row_count for fold in self.folds) != self.pooled_metrics.row_count:
            raise ValueError("contextual pooled metrics must cover every assessment row.")
        for field_name in (
            "median_fold_log_loss",
            "worst_fold_log_loss",
            "median_fold_brier_score",
            "worst_fold_brier_score",
        ):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{field_name} must be finite and non-negative.")
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True, slots=True)
class ContextAblationComparison:
    variant: ContextAblationVariant
    evaluated_fold_indexes: tuple[int, ...]
    context_minus_spy_log_loss: float
    context_minus_spy_brier_score: float
    context_minus_spy_accuracy: float
    lower_log_loss_fold_count: int
    lower_brier_fold_count: int

    def __post_init__(self) -> None:
        _contextual_definition(self.variant)
        if not self.evaluated_fold_indexes:
            raise ValueError("evaluated_fold_indexes must not be empty.")
        if self.evaluated_fold_indexes != tuple(sorted(set(self.evaluated_fold_indexes))):
            raise ValueError("evaluated_fold_indexes must be unique and increasing.")
        for field_name in (
            "context_minus_spy_log_loss",
            "context_minus_spy_brier_score",
            "context_minus_spy_accuracy",
        ):
            value = float(getattr(self, field_name))
            if not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite.")
            object.__setattr__(self, field_name, value)
        fold_count = len(self.evaluated_fold_indexes)
        if not 0 <= self.lower_log_loss_fold_count <= fold_count:
            raise ValueError("lower_log_loss_fold_count must lie within the evaluated fold count.")
        if not 0 <= self.lower_brier_fold_count <= fold_count:
            raise ValueError("lower_brier_fold_count must lie within the evaluated fold count.")


@dataclass(frozen=True, slots=True)
class ContextAblationStudy:
    policy_id: str
    context_feature_policy_id: str
    source_market_data_checksum: str
    source_schema_version: str
    scenario_schema_id: str
    benchmark_policy_id: str
    spy_candidate_id: str
    spy_feature_policy_id: str
    horizon_length: int
    development_through_session: date
    spy_only: ScenarioCandidateEvaluation
    contextual_evaluations: tuple[ContextAblationVariantEvaluation, ...]
    comparisons: tuple[ContextAblationComparison, ...]

    def __post_init__(self) -> None:
        if self.policy_id != MI2C_POLICY_ID:
            raise ValueError("policy_id must match the frozen MI-2C policy.")
        if self.context_feature_policy_id != MI2B_CONTEXT_FEATURE_POLICY_ID:
            raise ValueError("context_feature_policy_id must match the frozen MI-2B policy.")
        if self.benchmark_policy_id != MI1C_POLICY_ID:
            raise ValueError("benchmark_policy_id must match the frozen MI-1C policy.")
        if self.spy_candidate_id != MI1D_CANDIDATE_ID:
            raise ValueError("spy_candidate_id must match the frozen MI-1D candidate.")
        if self.spy_feature_policy_id != MI1D_FEATURE_POLICY_ID:
            raise ValueError("spy_feature_policy_id must match the frozen MI-1D feature policy.")
        _require_sha256(self.source_market_data_checksum, field_name="source_market_data_checksum")
        if self.spy_only.source_market_data_checksum != self.source_market_data_checksum:
            raise ValueError("SPY-only checksum must match the MI-2C study checksum.")
        if self.spy_only.source_schema_version != self.source_schema_version:
            raise ValueError("SPY-only source schema must match the MI-2C study schema.")
        if self.spy_only.scenario_schema_id != self.scenario_schema_id:
            raise ValueError("SPY-only scenario schema must match the MI-2C study schema.")
        if self.spy_only.horizon_length != self.horizon_length:
            raise ValueError("SPY-only horizon must match the MI-2C study horizon.")
        if self.spy_only.development_through_session != self.development_through_session:
            raise ValueError("SPY-only development cutoff must match the MI-2C study cutoff.")

        contextual_by_variant = {
            evaluation.variant: evaluation for evaluation in self.contextual_evaluations
        }
        expected_variants = set(ContextAblationVariant) - {ContextAblationVariant.SPY_ONLY}
        if set(contextual_by_variant) != expected_variants or len(self.contextual_evaluations) != 4:
            raise ValueError("study must contain all four contextual ablation evaluations once.")
        comparison_by_variant = {comparison.variant: comparison for comparison in self.comparisons}
        if set(comparison_by_variant) != expected_variants or len(self.comparisons) != 4:
            raise ValueError("study must contain all four contextual comparisons once.")

        spy_fold_indexes = tuple(fold.baseline_fold_index for fold in self.spy_only.folds)
        for variant in tuple(ContextAblationVariant)[1:]:
            evaluation = contextual_by_variant[variant]
            comparison = comparison_by_variant[variant]
            if (
                evaluation.source_market_data_checksum != self.source_market_data_checksum
                or evaluation.source_schema_version != self.source_schema_version
                or evaluation.scenario_schema_id != self.scenario_schema_id
                or evaluation.horizon_length != self.horizon_length
                or evaluation.development_through_session != self.development_through_session
            ):
                raise ValueError("contextual evaluation lineage must match the MI-2C study.")
            contextual_fold_indexes = tuple(fold.baseline_fold_index for fold in evaluation.folds)
            if contextual_fold_indexes != spy_fold_indexes:
                raise ValueError("all MI-2C variants must use the exact SPY-only retained folds.")
            if comparison.evaluated_fold_indexes != spy_fold_indexes:
                raise ValueError("comparison fold indexes must match the SPY-only retained folds.")
            _validate_comparison_arithmetic(self.spy_only, evaluation, comparison)

        object.__setattr__(
            self,
            "contextual_evaluations",
            tuple(contextual_by_variant[variant] for variant in tuple(ContextAblationVariant)[1:]),
        )
        object.__setattr__(
            self,
            "comparisons",
            tuple(comparison_by_variant[variant] for variant in tuple(ContextAblationVariant)[1:]),
        )

    def evaluation_for(self, variant: ContextAblationVariant) -> ScenarioCandidateEvaluation | ContextAblationVariantEvaluation:
        if variant == ContextAblationVariant.SPY_ONLY:
            return self.spy_only
        return next(
            evaluation for evaluation in self.contextual_evaluations if evaluation.variant == variant
        )

    def comparison_for(self, variant: ContextAblationVariant) -> ContextAblationComparison:
        if variant == ContextAblationVariant.SPY_ONLY:
            raise ValueError("SPY_ONLY is the reference and has no context-minus-SPY comparison.")
        return next(comparison for comparison in self.comparisons if comparison.variant == variant)


def evaluate_development_context_ablation(
    feature_set: FeatureSet,
    label_set: ScenarioLabelSet,
    benchmark: ScenarioBaselineBenchmark,
    context_history: SPYContextFeatureHistory,
) -> ContextAblationStudy:
    """Compare frozen MI-2C context groups on the exact retained MI-1D development rows."""

    spy_only = evaluate_development_multinomial_candidate(feature_set, label_set, benchmark)
    _validate_history_alignment(feature_set, label_set, context_history)
    spy_feature_by_session = _spy_feature_rows_by_session(feature_set)
    label_by_anchor = {label.anchor_session: label for label in label_set.labels}

    contextual_evaluations: list[ContextAblationVariantEvaluation] = []
    comparisons: list[ContextAblationComparison] = []
    for definition in MI2C_ABLATION_DEFINITIONS[1:]:
        folds = tuple(
            _fit_and_score_contextual_fold(
                definition=definition,
                spy_fold=spy_fold,
                label_set=label_set,
                label_by_anchor=label_by_anchor,
                spy_feature_by_session=spy_feature_by_session,
                context_history=context_history,
                feature_schema_version=feature_set.feature_schema_version,
            )
            for spy_fold in spy_only.folds
        )
        pooled_outcomes = tuple(outcome for fold in folds for outcome in fold.assessment_outcomes)
        pooled_probability_rows = tuple(row for fold in folds for row in fold.probability_rows)
        pooled_metrics = calculate_scenario_probability_metrics(
            pooled_outcomes,
            pooled_probability_rows,
        )
        fold_log_losses = [fold.metrics.multiclass_log_loss for fold in folds]
        fold_brier_scores = [fold.metrics.multiclass_brier_score for fold in folds]
        evaluation = ContextAblationVariantEvaluation(
            variant=definition.variant,
            feature_columns=definition.model_feature_columns,
            horizon_length=label_set.horizon.length,
            development_through_session=benchmark.development_through_session,
            source_market_data_checksum=label_set.source_market_data_checksum,
            source_schema_version=label_set.source_schema_version,
            scenario_schema_id=label_set.scenario_schema_id,
            folds=folds,
            pooled_metrics=pooled_metrics,
            median_fold_log_loss=statistics.median(fold_log_losses),
            worst_fold_log_loss=max(fold_log_losses),
            median_fold_brier_score=statistics.median(fold_brier_scores),
            worst_fold_brier_score=max(fold_brier_scores),
        )
        contextual_evaluations.append(evaluation)
        comparisons.append(_comparison_with_spy_only(spy_only, evaluation))

    return ContextAblationStudy(
        policy_id=MI2C_POLICY_ID,
        context_feature_policy_id=MI2B_CONTEXT_FEATURE_POLICY_ID,
        source_market_data_checksum=label_set.source_market_data_checksum,
        source_schema_version=label_set.source_schema_version,
        scenario_schema_id=label_set.scenario_schema_id,
        benchmark_policy_id=benchmark.policy_id,
        spy_candidate_id=spy_only.candidate_id,
        spy_feature_policy_id=spy_only.feature_policy_id,
        horizon_length=label_set.horizon.length,
        development_through_session=benchmark.development_through_session,
        spy_only=spy_only,
        contextual_evaluations=tuple(contextual_evaluations),
        comparisons=tuple(comparisons),
    )


def _validate_history_alignment(
    feature_set: FeatureSet,
    label_set: ScenarioLabelSet,
    context_history: SPYContextFeatureHistory,
) -> None:
    if context_history.source_market_data_checksum != feature_set.source_market_data_checksum:
        raise ValueError("historical context and feature market-data checksums must match.")
    if context_history.source_market_data_checksum != label_set.source_market_data_checksum:
        raise ValueError("historical context and label market-data checksums must match.")
    if context_history.source_schema_version != feature_set.source_schema_version:
        raise ValueError("historical context and feature source schemas must match.")
    if context_history.source_schema_version != label_set.source_schema_version:
        raise ValueError("historical context and label source schemas must match.")


def _spy_feature_rows_by_session(feature_set: FeatureSet) -> dict[date, tuple[float, ...]]:
    rows: dict[date, tuple[float, ...]] = {}
    for row in feature_set.data.loc[:, ["session", *MI1D_FEATURE_COLUMNS]].itertuples(
        index=False,
        name=None,
    ):
        session = cast(date, row[0])
        values = tuple(float(value) for value in row[1:])
        if any(not math.isfinite(value) for value in values):
            raise ValueError("MI-2C SPY features must contain only finite values.")
        rows[session] = values
    return rows


def _fit_and_score_contextual_fold(
    *,
    definition: ContextAblationDefinition,
    spy_fold: ScenarioCandidateFoldEvaluation,
    label_set: ScenarioLabelSet,
    label_by_anchor: dict[date, ScenarioLabel],
    spy_feature_by_session: dict[date, tuple[float, ...]],
    context_history: SPYContextFeatureHistory,
    feature_schema_version: str,
) -> ContextAblationFoldEvaluation:
    assessment_start = spy_fold.assessment_anchor_sessions[0]
    fit_labels = tuple(
        label
        for label in label_set.labels
        if label.outcome_session <= assessment_start
        and label.anchor_session in spy_feature_by_session
    )
    _validate_fit_matches_spy_reference(fit_labels, spy_fold)
    assessment_labels = _assessment_labels_for_spy_fold(spy_fold, label_by_anchor=label_by_anchor)

    fit_rows = tuple(
        _combined_feature_row(
            label.anchor_session,
            definition=definition,
            spy_feature_by_session=spy_feature_by_session,
            context_history=context_history,
        )
        for label in fit_labels
    )
    assessment_rows = tuple(
        _combined_feature_row(
            label.anchor_session,
            definition=definition,
            spy_feature_by_session=spy_feature_by_session,
            context_history=context_history,
        )
        for label in assessment_labels
    )
    outcomes_present = {label.outcome for label in fit_labels}
    if outcomes_present != set(ScenarioOutcome):
        raise ValueError("every MI-2C training fold must contain all three scenario classes.")

    train_x = pd.DataFrame(
        fit_rows,
        columns=list(definition.model_feature_columns),
        dtype="float64",
    )
    train_y = pd.Series(
        [tuple(ScenarioOutcome).index(label.outcome) for label in fit_labels],
        dtype="int64",
    )
    assessment_x = pd.DataFrame(
        assessment_rows,
        columns=list(definition.model_feature_columns),
        dtype="float64",
    )

    scaler = StandardScaler()
    scaled_train = scaler.fit_transform(train_x)
    estimator = LogisticRegression(
        C=MI1D_LOGISTIC_C,
        solver=MI1D_LOGISTIC_SOLVER,
        max_iter=MI1D_LOGISTIC_MAX_ITER,
        tol=MI1D_LOGISTIC_TOL,
        fit_intercept=True,
        class_weight=None,
    )
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always", ConvergenceWarning)
        try:
            estimator.fit(scaled_train, train_y)
        except ValueError as exc:
            raise ValueError("MI-2C logistic-regression fit failed.") from exc
    if any(issubclass(warning.category, ConvergenceWarning) for warning in captured_warnings):
        raise ValueError("MI-2C logistic regression did not converge under the frozen policy.")

    estimator_any = cast(Any, estimator)
    if tuple(int(value) for value in estimator_any.classes_) != tuple(range(len(ScenarioOutcome))):
        raise ValueError("MI-2C fitted classes must match canonical scenario encoding.")
    probability_matrix = estimator.predict_proba(scaler.transform(assessment_x))
    probability_rows = tuple(
        tuple(
            ScenarioProbability(outcome=outcome, probability=float(row[class_index]))
            for class_index, outcome in enumerate(ScenarioOutcome)
        )
        for row in probability_matrix
    )
    outcomes = tuple(label.outcome for label in assessment_labels)
    metrics = calculate_scenario_probability_metrics(outcomes, probability_rows)

    scaler_any = cast(Any, scaler)
    snapshot = ContextAblationModelSnapshot(
        policy_id=MI2C_POLICY_ID,
        candidate_id=MI2C_CONTEXT_CANDIDATE_ID,
        variant=definition.variant,
        feature_columns=definition.model_feature_columns,
        context_feature_policy_id=MI2B_CONTEXT_FEATURE_POLICY_ID,
        feature_schema_version=feature_schema_version,
        sklearn_version=sklearn.__version__,
        fit_row_count=len(fit_labels),
        fit_first_anchor_session=fit_labels[0].anchor_session,
        fit_last_anchor_session=fit_labels[-1].anchor_session,
        fit_last_outcome_session=max(label.outcome_session for label in fit_labels),
        fit_context_digest=_context_digest(
            tuple(context_history.bundle_for(label.anchor_session) for label in fit_labels)
        ),
        scaler_mean=tuple(float(value) for value in scaler_any.mean_.tolist()),
        scaler_scale=tuple(float(value) for value in scaler_any.scale_.tolist()),
        class_order=tuple(ScenarioOutcome),
        coefficients=tuple(
            tuple(float(value) for value in row) for row in estimator_any.coef_.tolist()
        ),
        intercepts=tuple(float(value) for value in estimator_any.intercept_.tolist()),
    )
    return ContextAblationFoldEvaluation(
        baseline_fold_index=spy_fold.baseline_fold_index,
        model_snapshot=snapshot,
        assessment_anchor_sessions=tuple(label.anchor_session for label in assessment_labels),
        assessment_outcome_sessions=tuple(label.outcome_session for label in assessment_labels),
        assessment_outcomes=outcomes,
        probability_rows=probability_rows,
        metrics=metrics,
    )


def _validate_fit_matches_spy_reference(
    fit_labels: tuple[ScenarioLabel, ...],
    spy_fold: ScenarioCandidateFoldEvaluation,
) -> None:
    snapshot = spy_fold.model_snapshot
    if len(fit_labels) != snapshot.fit_row_count:
        raise ValueError("MI-2C fit row count must exactly match the SPY-only reference fold.")
    if not fit_labels:
        raise ValueError("MI-2C fit labels must not be empty.")
    if fit_labels[0].anchor_session != snapshot.fit_first_anchor_session:
        raise ValueError("MI-2C first fit anchor must match the SPY-only reference fold.")
    if fit_labels[-1].anchor_session != snapshot.fit_last_anchor_session:
        raise ValueError("MI-2C last fit anchor must match the SPY-only reference fold.")
    if max(label.outcome_session for label in fit_labels) != snapshot.fit_last_outcome_session:
        raise ValueError("MI-2C last fit outcome must match the SPY-only reference fold.")


def _assessment_labels_for_spy_fold(
    spy_fold: ScenarioCandidateFoldEvaluation,
    *,
    label_by_anchor: dict[date, ScenarioLabel],
) -> tuple[ScenarioLabel, ...]:
    labels: list[ScenarioLabel] = []
    for anchor, expected_outcome_session, expected_outcome in zip(
        spy_fold.assessment_anchor_sessions,
        spy_fold.assessment_outcome_sessions,
        spy_fold.assessment_outcomes,
        strict=True,
    ):
        label = label_by_anchor.get(anchor)
        if label is None:
            raise ValueError("SPY-only assessment anchor is missing from the scenario labels.")
        if label.outcome_session != expected_outcome_session or label.outcome != expected_outcome:
            raise ValueError("MI-2C assessment rows must exactly match the SPY-only reference.")
        labels.append(label)
    return tuple(labels)


def _combined_feature_row(
    anchor_session: date,
    *,
    definition: ContextAblationDefinition,
    spy_feature_by_session: dict[date, tuple[float, ...]],
    context_history: SPYContextFeatureHistory,
) -> tuple[float, ...]:
    spy_values = spy_feature_by_session.get(anchor_session)
    if spy_values is None:
        raise ValueError("MI-2C requires every reference anchor to have a SPY feature row.")
    bundle = context_history.bundle_for(anchor_session)
    values_by_id = {feature.feature_id: feature.value for feature in bundle.features}
    context_values = tuple(values_by_id[feature_id] for feature_id in definition.context_feature_ids)
    combined = (*spy_values, *context_values)
    if any(not math.isfinite(value) for value in combined):
        raise ValueError("MI-2C model features must contain only finite values.")
    return combined


def _comparison_with_spy_only(
    spy_only: ScenarioCandidateEvaluation,
    contextual: ContextAblationVariantEvaluation,
) -> ContextAblationComparison:
    if len(spy_only.folds) != len(contextual.folds):
        raise ValueError("MI-2C comparisons require matching SPY and contextual fold counts.")
    fold_indexes = tuple(fold.baseline_fold_index for fold in spy_only.folds)
    for spy_fold, context_fold in zip(spy_only.folds, contextual.folds, strict=True):
        _validate_fold_rows_match(spy_fold, context_fold)
    return ContextAblationComparison(
        variant=contextual.variant,
        evaluated_fold_indexes=fold_indexes,
        context_minus_spy_log_loss=(
            contextual.pooled_metrics.multiclass_log_loss
            - spy_only.pooled_metrics.multiclass_log_loss
        ),
        context_minus_spy_brier_score=(
            contextual.pooled_metrics.multiclass_brier_score
            - spy_only.pooled_metrics.multiclass_brier_score
        ),
        context_minus_spy_accuracy=(
            contextual.pooled_metrics.accuracy - spy_only.pooled_metrics.accuracy
        ),
        lower_log_loss_fold_count=sum(
            context_fold.metrics.multiclass_log_loss < spy_fold.metrics.multiclass_log_loss
            for spy_fold, context_fold in zip(spy_only.folds, contextual.folds, strict=True)
        ),
        lower_brier_fold_count=sum(
            context_fold.metrics.multiclass_brier_score < spy_fold.metrics.multiclass_brier_score
            for spy_fold, context_fold in zip(spy_only.folds, contextual.folds, strict=True)
        ),
    )


def _validate_fold_rows_match(
    spy_fold: ScenarioCandidateFoldEvaluation,
    context_fold: ContextAblationFoldEvaluation,
) -> None:
    if context_fold.baseline_fold_index != spy_fold.baseline_fold_index:
        raise ValueError("contextual fold index must match the SPY-only reference.")
    if context_fold.model_snapshot.fit_row_count != spy_fold.model_snapshot.fit_row_count:
        raise ValueError("contextual fit row count must match the SPY-only reference.")
    if context_fold.assessment_anchor_sessions != spy_fold.assessment_anchor_sessions:
        raise ValueError("contextual assessment anchors must match the SPY-only reference.")
    if context_fold.assessment_outcome_sessions != spy_fold.assessment_outcome_sessions:
        raise ValueError("contextual assessment outcome sessions must match the SPY-only reference.")
    if context_fold.assessment_outcomes != spy_fold.assessment_outcomes:
        raise ValueError("contextual assessment outcomes must match the SPY-only reference.")


def _validate_comparison_arithmetic(
    spy_only: ScenarioCandidateEvaluation,
    contextual: ContextAblationVariantEvaluation,
    comparison: ContextAblationComparison,
) -> None:
    expected = (
        contextual.pooled_metrics.multiclass_log_loss
        - spy_only.pooled_metrics.multiclass_log_loss,
        contextual.pooled_metrics.multiclass_brier_score
        - spy_only.pooled_metrics.multiclass_brier_score,
        contextual.pooled_metrics.accuracy - spy_only.pooled_metrics.accuracy,
    )
    actual = (
        comparison.context_minus_spy_log_loss,
        comparison.context_minus_spy_brier_score,
        comparison.context_minus_spy_accuracy,
    )
    if any(
        not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
        for left, right in zip(expected, actual, strict=True)
    ):
        raise ValueError("context-minus-SPY pooled comparison deltas are inconsistent.")
    expected_log_wins = sum(
        context_fold.metrics.multiclass_log_loss < spy_fold.metrics.multiclass_log_loss
        for spy_fold, context_fold in zip(spy_only.folds, contextual.folds, strict=True)
    )
    expected_brier_wins = sum(
        context_fold.metrics.multiclass_brier_score < spy_fold.metrics.multiclass_brier_score
        for spy_fold, context_fold in zip(spy_only.folds, contextual.folds, strict=True)
    )
    if comparison.lower_log_loss_fold_count != expected_log_wins:
        raise ValueError("lower-log-loss fold count is inconsistent with fold metrics.")
    if comparison.lower_brier_fold_count != expected_brier_wins:
        raise ValueError("lower-Brier fold count is inconsistent with fold metrics.")


def _context_digest(bundles: tuple[SPYContextFeatureBundle, ...]) -> str:
    digest = hashlib.sha256()
    for bundle in bundles:
        digest.update(MI2B_CONTEXT_FEATURE_POLICY_ID.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bundle.anchor_session.isoformat().encode("ascii"))
        digest.update(b"\0")
        digest.update(bundle.as_of.isoformat().encode("ascii"))
        digest.update(b"\0")
        digest.update(bundle.target_snapshot_id.encode("utf-8"))
        digest.update(b"\0")
        for snapshot_id in bundle.context_snapshot_ids:
            digest.update(snapshot_id.encode("utf-8"))
            digest.update(b"\0")
        for feature in bundle.features:
            digest.update(feature.feature_id.encode("utf-8"))
            digest.update(b"=")
            digest.update(float(feature.value).hex().encode("ascii"))
            digest.update(b"\0")
    return digest.hexdigest()


def _contextual_definition(variant: ContextAblationVariant) -> ContextAblationDefinition:
    if not isinstance(variant, ContextAblationVariant):
        raise ValueError("variant must be a ContextAblationVariant.")
    if variant == ContextAblationVariant.SPY_ONLY:
        raise ValueError("SPY_ONLY uses the frozen MI-1D candidate, not a contextual model.")
    return _DEFINITION_BY_VARIANT[variant]


def _require_sha256(value: str, *, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest.")
