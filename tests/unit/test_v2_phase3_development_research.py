from __future__ import annotations

import importlib
import inspect
import json
import math
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pandas as pd
import pytest

from spy_market_agent.datasets.labels import build_forward_label_set
from spy_market_agent.datasets.models import LABEL_COLUMNS, TradingCostAssumptions
from spy_market_agent.features.models import FEATURE_COLUMNS
from spy_market_agent.market_data.calendar import XNYSCalendar
from spy_market_agent.market_data.checksum import compute_market_data_checksum
from spy_market_agent.market_data.models import (
    SCHEMA_VERSION as MARKET_DATA_SCHEMA_VERSION,
)
from spy_market_agent.market_data.models import (
    MarketDataBatch,
    MarketDataMetadata,
)
from spy_market_agent.modeling.models import (
    GRADIENT_BOOSTING_MODEL,
    LOGISTIC_REGRESSION_MODEL,
    fixed_model_parameters,
)
from spy_market_agent.research.campaign import ResearchCampaignConfig, campaign_config_identity
from spy_market_agent.research.candidates import (
    EXTRA_TREES_GRID,
    HIST_GRADIENT_BOOSTING_GRID,
    LOGISTIC_RESEARCH_GRID,
    development_hyperparameter_searches,
    development_model_registry,
)
from spy_market_agent.research.diagnostics import fold_drift_diagnostics, fold_regime_diagnostics
from spy_market_agent.research.errors import LeakageValidationError
from spy_market_agent.research.evaluation import evaluate_calibration_variant
from spy_market_agent.research.features import (
    BASELINE_FAMILY_ORDER,
    DOLLAR_VOLUME_FAMILY,
    DRAWDOWN_POSITION_FAMILY,
    PHASE3_RESEARCH_FEATURE_COLUMNS,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_FEATURE_SCHEMA_VERSION,
    VOLATILITY_STRUCTURE_FAMILY,
    ResearchSupervisedDataset,
    build_research_feature_matrix,
    build_research_supervised_dataset,
    development_research_feature_registry,
    feature_columns_for_families,
)
from spy_market_agent.research.folds import construct_walk_forward_manifest
from spy_market_agent.research.leakage import validate_phase2_final_test_isolation
from spy_market_agent.research.metrics import calculate_research_classification_metrics
from spy_market_agent.research.models import (
    CalibrationPolicy,
    DatasetLineage,
    FoldPolicy,
    RuntimeLineage,
)
from spy_market_agent.research.runner import run_development_campaign
from spy_market_agent.research.selection import NO_CANDIDATE_PROMOTION

CREATED_AT = datetime(2026, 8, 10, 12, tzinfo=UTC)


def _market_data(row_count: int = 1030, *, constant_close: bool = False) -> MarketDataBatch:
    sessions = XNYSCalendar().sessions_between(date(2020, 1, 2), date(2024, 3, 29))[:row_count]
    closes: list[float] = []
    for index in range(row_count):
        if constant_close:
            close = 100.0
        else:
            close = 100.0 + min(index, 40) * 0.8 - max(0, index - 40) * 0.12
            close += 1.5 * math.sin(index / 7.0)
        closes.append(close)
    frame = pd.DataFrame(
        {
            "session": sessions,
            "open": [close * (1.0 + 0.001 * math.sin(index)) for index, close in enumerate(closes)],
            "high": [close * 1.004 for close in closes],
            "low": [close * 0.996 for close in closes],
            "close": closes,
            "volume": [80_000_000 + index * 1000 for index in range(row_count)],
        },
        columns=["session", "open", "high", "low", "close", "volume"],
    )
    frame["open"] = frame["open"].astype("float64")
    frame["high"] = frame["high"].astype("float64")
    frame["low"] = frame["low"].astype("float64")
    frame["close"] = frame["close"].astype("float64")
    frame["volume"] = frame["volume"].astype("int64")
    return MarketDataBatch(
        data=frame,
        metadata=MarketDataMetadata(
            provider_name="synthetic",
            downloaded_at=CREATED_AT,
            created_at=CREATED_AT,
            first_session=sessions[0],
            last_session=sessions[-1],
            row_count=len(frame),
            dataset_checksum=compute_market_data_checksum(frame),
            schema_version=MARKET_DATA_SCHEMA_VERSION,
            source_description="synthetic Phase 3 development fixture",
        ),
    )


def _research_supervised(row_count: int = 1030) -> ResearchSupervisedDataset:
    market_data = _market_data(row_count)
    features = build_research_feature_matrix(market_data, created_at=CREATED_AT)
    labels = build_forward_label_set(
        market_data,
        cost_assumptions=TradingCostAssumptions(
            commission_bps_per_side=Decimal("0.125"),
            slippage_bps_per_side=Decimal("0.25"),
        ),
        created_at=CREATED_AT,
    )
    return build_research_supervised_dataset(features, labels, created_at=CREATED_AT)


def _dataset_lineage(market_data: MarketDataBatch) -> DatasetLineage:
    return DatasetLineage(
        dataset_id="synthetic-phase3-development",
        canonical_dataset_checksum=market_data.metadata.dataset_checksum,
        provider="synthetic",
        feed="sip",
        timeframe="1Day",
        adjustment="all",
        first_session=market_data.metadata.first_session,
        last_session=market_data.metadata.last_session,
    )


def test_research_features_match_hand_calculated_trailing_formulas() -> None:
    market_data = _market_data(90)
    matrix = build_research_feature_matrix(market_data, created_at=CREATED_AT)
    source = market_data.data.reset_index(drop=True)
    source_index = 60
    row = matrix.data.iloc[0]
    close = source["close"].astype("float64")
    volume = source["volume"].astype("float64")
    returns = close / close.shift(1) - 1.0
    realized_5 = returns.iloc[source_index - 4 : source_index + 1].std(ddof=0)
    realized_20 = returns.iloc[source_index - 19 : source_index + 1].std(ddof=0)
    trailing_high_20 = close.iloc[source_index - 19 : source_index + 1].max()
    trailing_low_20 = close.iloc[source_index - 19 : source_index + 1].min()
    trailing_high_60 = close.iloc[source_index - 59 : source_index + 1].max()
    log_dollar_volume = (close * volume).map(math.log1p)
    expected_log_dollar_deviation = (
        log_dollar_volume.iloc[source_index]
        - log_dollar_volume.iloc[source_index - 19 : source_index + 1].mean()
    )

    assert row["session"] == source.iloc[source_index]["session"]
    assert row["drawdown_20d"] == pytest.approx(close.iloc[source_index] / trailing_high_20 - 1.0)
    assert row["drawdown_60d"] == pytest.approx(close.iloc[source_index] / trailing_high_60 - 1.0)
    assert row["distance_to_high_20d"] == pytest.approx(
        close.iloc[source_index] / trailing_high_20 - 1.0
    )
    assert row["distance_to_low_20d"] == pytest.approx(
        close.iloc[source_index] / trailing_low_20 - 1.0
    )
    assert row["realized_volatility_ratio_5_20"] == pytest.approx(realized_5 / realized_20)
    assert row["log_dollar_volume_deviation_20"] == pytest.approx(expected_log_dollar_deviation)
    for column in RESEARCH_FEATURE_COLUMNS:
        assert str(matrix.data[column].dtype) == "float64"


def test_research_features_use_trailing_data_and_reject_nonfinite_post_warmup() -> None:
    market_data = _market_data(90)
    original = build_research_feature_matrix(market_data, created_at=CREATED_AT).data.iloc[0]
    mutated_frame = market_data.data.copy(deep=True)
    mutated_frame.loc[80:, "close"] = mutated_frame.loc[80:, "close"] * 10.0
    mutated = MarketDataBatch(
        data=mutated_frame,
        metadata=market_data.metadata.model_copy(
            update={
                "dataset_checksum": compute_market_data_checksum(mutated_frame),
                "row_count": len(mutated_frame),
            }
        ),
    )
    changed = build_research_feature_matrix(mutated, created_at=CREATED_AT).data.iloc[0]
    for column in PHASE3_RESEARCH_FEATURE_COLUMNS:
        assert changed[column] == pytest.approx(original[column])

    with pytest.raises(LeakageValidationError, match="undefined_post_warmup_research_feature"):
        build_research_feature_matrix(_market_data(90, constant_close=True), created_at=CREATED_AT)


def test_research_supervised_dataset_alignment_does_not_modify_v1_feature_contract() -> None:
    supervised = _research_supervised()
    assert FEATURE_COLUMNS == (
        "close_return_1d",
        "close_return_5d",
        "close_return_20d",
        "overnight_gap_1d",
        "intraday_return_1d",
        "range_pct_1d",
        "close_to_sma_5",
        "close_to_sma_20",
        "realized_volatility_5",
        "realized_volatility_20",
        "log_volume_change_1d",
        "log_volume_deviation_20",
    )
    assert supervised.metadata.feature_schema_version == RESEARCH_FEATURE_SCHEMA_VERSION
    assert tuple(supervised.features.columns) == ("session", *RESEARCH_FEATURE_COLUMNS)
    assert tuple(supervised.labels.columns) == LABEL_COLUMNS
    assert supervised.features["session"].to_list() == supervised.labels["session"].to_list()

    bad_features = supervised.features.copy(deep=True)
    bad_features["target"] = supervised.labels["target"]
    with pytest.raises(LeakageValidationError, match="forbidden_model_feature_columns"):
        ResearchSupervisedDataset(
            features=bad_features,
            labels=supervised.labels,
            metadata=supervised.metadata,
        )


def test_phase3_global_warmup_and_fold_policy_identity_are_deterministic() -> None:
    market_data = _market_data()
    supervised = _research_supervised()
    lineage = _dataset_lineage(market_data)
    policy = FoldPolicy(feature_warmup_rows=60)
    manifest = construct_walk_forward_manifest(
        supervised,
        dataset_lineage=lineage,
        runtime_lineage=_runtime_lineage(),
        policy=policy,
    )
    repeated = construct_walk_forward_manifest(
        supervised,
        dataset_lineage=lineage,
        runtime_lineage=_runtime_lineage(),
        policy=policy,
    )

    assert manifest.fold_policy.feature_warmup_rows == 60
    assert manifest.fold_manifest_id == repeated.fold_manifest_id
    assert [fold.fold_id for fold in manifest.folds] == [fold.fold_id for fold in repeated.folds]
    assert len(manifest.folds) >= 3
    first = manifest.folds[0]
    assert first.training.row_count == 756
    assert len(first.boundary_excluded_sessions) == 6
    assert first.assessment.row_count == 126
    assert first.training.last_exit_session == first.boundary_excluded_sessions[-1]
    assert first.boundary_excluded_sessions[-1] < first.assessment.first_prediction_session


def test_development_model_grids_and_fixed_baselines_are_predeclared() -> None:
    registry = development_model_registry()
    assert len(LOGISTIC_RESEARCH_GRID) == 6
    assert len(HIST_GRADIENT_BOOSTING_GRID) == 8
    assert len(EXTRA_TREES_GRID) == 12
    assert len(registry.models) == 28
    logistic = next(
        model for model in registry.models if model.model_name == LOGISTIC_REGRESSION_MODEL
    )
    gradient = next(
        model for model in registry.models if model.model_name == GRADIENT_BOOSTING_MODEL
    )
    assert (
        logistic.parameters
        == fixed_model_parameters(LOGISTIC_REGRESSION_MODEL, random_seed=42).parameters
    )
    assert (
        gradient.parameters
        == fixed_model_parameters(GRADIENT_BOOSTING_MODEL, random_seed=42).parameters
    )
    assert all(
        any(name.endswith("random_state") and value == 42 for name, value in model.parameters)
        for model in registry.models
    )

    searches = development_hyperparameter_searches()
    assert [search.trial_count for search in searches] == [6, 8, 12]


def test_research_campaign_config_identity_includes_selection_sensitive_values() -> None:
    config = ResearchCampaignConfig()
    same = ResearchCampaignConfig()
    assert campaign_config_identity(config) == campaign_config_identity(same)
    with pytest.raises(ValueError, match="material_roc_auc_delta"):
        ResearchCampaignConfig(material_roc_auc_delta=0.0)
    assert config.candidate_selection_config().material_roc_auc_delta == 0.01


def test_ece_and_reliability_bins_are_exact() -> None:
    metrics = calculate_research_classification_metrics(
        model_name="candidate",
        fold_id="fold",
        targets=(0, 1, 1, 0),
        probabilities=(0.05, 0.15, 0.85, 0.95),
        reliability_bin_count=2,
    )
    assert metrics.metrics["expected_calibration_error"].value == pytest.approx(0.4)
    assert metrics.reliability_bins[0]["absolute_calibration_gap"] == pytest.approx(0.4)
    assert metrics.reliability_bins[0]["weighted_contribution"] == pytest.approx(0.2)
    assert metrics.reliability_bins[1]["weighted_contribution"] == pytest.approx(0.2)


def test_feature_registry_and_feature_family_columns_are_deterministic() -> None:
    registry = development_research_feature_registry(
        enabled_families=(*BASELINE_FAMILY_ORDER, DRAWDOWN_POSITION_FAMILY)
    )
    assert registry.feature_schema == RESEARCH_FEATURE_SCHEMA_VERSION
    assert DRAWDOWN_POSITION_FAMILY in registry.enabled_feature_families
    assert VOLATILITY_STRUCTURE_FAMILY not in registry.enabled_feature_families
    assert DOLLAR_VOLUME_FAMILY not in registry.enabled_feature_families
    columns = feature_columns_for_families((*BASELINE_FAMILY_ORDER, DRAWDOWN_POSITION_FAMILY))
    assert columns[: len(FEATURE_COLUMNS)] == FEATURE_COLUMNS
    assert columns[-4:] == (
        "drawdown_20d",
        "drawdown_60d",
        "distance_to_high_20d",
        "distance_to_low_20d",
    )


def test_calibration_variants_fit_without_outer_assessment_rows() -> None:
    market_data = _market_data()
    supervised = _research_supervised()
    manifest = construct_walk_forward_manifest(
        supervised,
        dataset_lineage=_dataset_lineage(market_data),
        runtime_lineage=_runtime_lineage(),
        policy=FoldPolicy(feature_warmup_rows=60),
    )
    model_definition = next(
        model
        for model in development_model_registry().models
        if model.model_name == LOGISTIC_REGRESSION_MODEL
    )
    for policy in (
        CalibrationPolicy(
            calibration_policy_id="phase3-sigmoid-platt-calibration-v1",
            method="sigmoid",
        ),
        CalibrationPolicy(
            calibration_policy_id="phase3-isotonic-calibration-v1",
            method="isotonic",
        ),
    ):
        result = evaluate_calibration_variant(
            supervised=supervised,
            fold_manifest=manifest,
            config=ResearchCampaignConfig(),
            feature_families=BASELINE_FAMILY_ORDER,
            model_definition=model_definition,
            policy=policy,
        )
        failures = tuple(fold.failure_reason for fold in result.fold_evaluations)
        assert {fold.status for fold in result.fold_evaluations} == {"completed"}, failures
        assert all(fold.metric_set is not None for fold in result.fold_evaluations)


def test_regime_and_drift_diagnostics_use_training_derived_boundaries() -> None:
    market_data = _market_data()
    supervised = _research_supervised()
    manifest = construct_walk_forward_manifest(
        supervised,
        dataset_lineage=_dataset_lineage(market_data),
        runtime_lineage=_runtime_lineage(),
        policy=FoldPolicy(feature_warmup_rows=60),
    )
    fold = manifest.folds[0]
    probabilities = (0.5,) * fold.assessment.row_count
    metrics = calculate_research_classification_metrics(
        model_name="constant",
        fold_id=fold.fold_id,
        targets=tuple(
            int(value)
            for value in supervised.labels.iloc[756 + 6 : 756 + 6 + fold.assessment.row_count][
                "target"
            ].to_list()
        ),
        probabilities=probabilities,
    )
    config = ResearchCampaignConfig()

    regime = fold_regime_diagnostics(
        market_data=market_data,
        supervised=supervised,
        fold=fold,
        probabilities=probabilities,
        config=config,
    )
    drift = fold_drift_diagnostics(
        supervised=supervised,
        fold=fold,
        feature_columns=("close_return_1d", "realized_volatility_20"),
        probabilities=probabilities,
        metrics=metrics,
        config=config,
    )

    training_values = supervised.features.iloc[:756]["realized_volatility_20"].astype("float64")
    assert regime["volatility_threshold"] == pytest.approx(float(training_values.median()))
    assert regime["selection_use"] == "descriptive_only_not_used_for_candidate_selection"
    feature_drift = cast(dict[str, dict[str, object]], drift["feature_distribution_drift"])
    close_return_drift = feature_drift["close_return_1d"]
    assert close_return_drift["undefined_reason"] is None
    assert math.isfinite(cast(float, close_return_drift["psi"]))
    drawdown_cells = cast(list[dict[str, object]], regime["drawdown"])
    assert all("small_sample" in cell for cell in drawdown_cells)


def test_phase2_final_test_references_are_rejected_before_development_loading() -> None:
    protected_names = (
        "final_test_results.json",
        "FINAL_TEST_PREDICTIONS.JSON",
        "phase2_final_test_strategy_rows.json",
        "artifacts/benchmarks/locked/final_test_regime_results.json",
    )
    for name in protected_names:
        with pytest.raises(LeakageValidationError, match="phase2_final_test_artifact_rejected"):
            validate_phase2_final_test_isolation((name,))
        with pytest.raises(LeakageValidationError, match="phase2_final_test_artifact_rejected"):
            run_development_campaign(
                manifest_path=Path(name),
                data_root=Path("data"),
                campaign_config_path=Path("configs/research/phase3_development_campaign.json"),
            )


def test_research_cli_has_no_broker_or_trading_client_imports() -> None:
    cli = importlib.import_module("spy_market_agent.research.cli")
    source = inspect.getsource(cli)
    forbidden_terms = (
        "alpaca_paper",
        "PaperTrading",
        "Broker",
        "submit_order",
        "execution_service",
    )
    assert all(term not in source for term in forbidden_terms)


def test_no_candidate_promotion_constant_is_valid_result() -> None:
    assert NO_CANDIDATE_PROMOTION == "NO CANDIDATE PROMOTION"


def test_committed_campaign_config_is_valid() -> None:
    config_path = Path("configs/research/phase3_development_campaign.json")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    config = ResearchCampaignConfig.model_validate(payload)
    assert config.global_feature_warmup_rows == 60
    assert config.protected_evaluation_authorized is False
    assert config.strategy_optimization_authorized is False


def _runtime_lineage() -> RuntimeLineage:
    return RuntimeLineage(
        git_commit_sha="abc123",
        package_version="2.0.0a2",
        python_version="3.12.13",
        dependency_versions={"pandas": "2.2.test", "scikit-learn": "1.7.test"},
    )
