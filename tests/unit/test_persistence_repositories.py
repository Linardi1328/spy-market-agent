from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from spy_market_agent.persistence import (
    PERSISTENCE_SCHEMA_VERSION,
    PersistenceConflictError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
    PersistenceSchemaError,
    SQLiteArtifactRepository,
    connect_database,
    initialize_database,
)
from unit.phase7_helpers import (
    BACKTEST_RUN_ID,
    MARKET_RUN_ID,
    MODEL_RUN_ID,
    initialized_repository,
    make_phase7_artifacts,
)


def test_database_initialization_is_explicit_idempotent_and_enables_foreign_keys(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase7.sqlite3"

    initialize_database(database_path)
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        versions = connection.execute("SELECT version FROM schema_migrations").fetchall()
        assert [row["version"] for row in versions] == [PERSISTENCE_SCHEMA_VERSION]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO model_predictions (
                    run_id, sequence_number, session, probability_positive,
                    predicted_class, target
                )
                VALUES ('missing', 0, '2025-01-02', 0.5, 1, 1)
                """
            )
    finally:
        connection.close()


def test_repository_requires_initialized_database(tmp_path: Path) -> None:
    repository = SQLiteArtifactRepository(tmp_path / "missing.sqlite3")

    with pytest.raises(PersistenceSchemaError, match="initialized"):
        repository.list_model_runs()


def test_market_data_round_trip_and_mutation_isolation(tmp_path: Path) -> None:
    artifacts = make_phase7_artifacts()
    repository = initialized_repository(tmp_path / "phase7.sqlite3")
    original_frame = artifacts.market_data.data.copy(deep=True)

    repository.save_market_data_batch(MARKET_RUN_ID, artifacts.market_data)
    artifacts.market_data.data.loc[0, "open"] = 999.0
    loaded = repository.load_market_data_batch(MARKET_RUN_ID)
    loaded.data.loc[0, "open"] = 888.0
    reloaded = repository.load_market_data_batch(MARKET_RUN_ID)

    pd.testing.assert_frame_equal(reloaded.data, original_frame)
    assert reloaded.metadata.dataset_checksum == artifacts.market_data.metadata.dataset_checksum


def test_final_evaluation_and_backtest_round_trips_preserve_values_and_order(
    tmp_path: Path,
) -> None:
    artifacts = make_phase7_artifacts()
    repository = initialized_repository(tmp_path / "phase7.sqlite3")

    repository.save_final_test_evaluation(MODEL_RUN_ID, artifacts.evaluation)
    repository.save_backtest_result(BACKTEST_RUN_ID, artifacts.backtest)
    loaded_evaluation = repository.load_final_test_evaluation(MODEL_RUN_ID)
    loaded_backtest = repository.load_backtest_result(BACKTEST_RUN_ID)

    pd.testing.assert_frame_equal(
        loaded_evaluation.prediction_set.data,
        artifacts.evaluation.prediction_set.data,
    )
    assert loaded_evaluation.locked_selection == artifacts.evaluation.locked_selection
    assert loaded_backtest.metrics == artifacts.backtest.metrics
    assert loaded_backtest.cost_assumptions.commission_bps_per_side == (
        artifacts.backtest.cost_assumptions.commission_bps_per_side
    )
    assert loaded_backtest.cost_assumptions.slippage_bps_per_side == (
        artifacts.backtest.cost_assumptions.slippage_bps_per_side
    )
    pd.testing.assert_frame_equal(
        loaded_backtest.proposed_orders,
        artifacts.backtest.proposed_orders,
    )
    pd.testing.assert_frame_equal(
        loaded_backtest.risk_decisions,
        artifacts.backtest.risk_decisions,
    )
    pd.testing.assert_frame_equal(loaded_backtest.fills, artifacts.backtest.fills)
    pd.testing.assert_frame_equal(loaded_backtest.portfolio, artifacts.backtest.portfolio)
    pd.testing.assert_frame_equal(
        loaded_backtest.execution_prices.data,
        artifacts.backtest.execution_prices.data,
    )


def test_duplicate_run_ids_and_missing_records_raise_structured_errors(tmp_path: Path) -> None:
    artifacts = make_phase7_artifacts()
    repository = initialized_repository(tmp_path / "phase7.sqlite3")

    repository.save_final_test_evaluation(MODEL_RUN_ID, artifacts.evaluation)
    with pytest.raises(PersistenceConflictError, match=MODEL_RUN_ID):
        repository.save_final_test_evaluation(MODEL_RUN_ID, artifacts.evaluation)
    with pytest.raises(PersistenceNotFoundError, match="not found"):
        repository.load_backtest_result("missing-backtest")


def test_transaction_rolls_back_when_nested_insert_fails(tmp_path: Path) -> None:
    artifacts = make_phase7_artifacts()
    database_path = tmp_path / "phase7.sqlite3"
    repository = initialized_repository(database_path)
    connection = connect_database(database_path)
    try:
        connection.execute(
            """
            CREATE TRIGGER fail_model_prediction_insert
            BEFORE INSERT ON model_predictions
            BEGIN
                SELECT RAISE(ABORT, 'forced prediction failure');
            END
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PersistenceIntegrityError, match="integrity"):
        repository.save_final_test_evaluation(MODEL_RUN_ID, artifacts.evaluation)

    connection = connect_database(database_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0]
        assert count == 0
    finally:
        connection.close()


def test_tampered_rows_and_unsupported_schema_versions_fail_safely(tmp_path: Path) -> None:
    artifacts = make_phase7_artifacts()
    database_path = tmp_path / "phase7.sqlite3"
    repository = initialized_repository(database_path)
    repository.save_final_test_evaluation(MODEL_RUN_ID, artifacts.evaluation)

    connection = connect_database(database_path)
    try:
        connection.execute(
            "UPDATE model_predictions SET probability_positive = 2.0 WHERE run_id = ?",
            (MODEL_RUN_ID,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PersistenceIntegrityError, match="reconstruction"):
        repository.load_final_test_evaluation(MODEL_RUN_ID)

    connection = connect_database(database_path)
    try:
        connection.execute(
            "INSERT INTO schema_migrations(version) VALUES ('spy-sqlite-persistence-v999')"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PersistenceSchemaError, match="unsupported"):
        repository.list_model_runs()


def test_backtest_source_checksum_tampering_and_independent_reads_fail_safely(
    tmp_path: Path,
) -> None:
    artifacts = make_phase7_artifacts()
    database_path = tmp_path / "phase7.sqlite3"
    first_repository = initialized_repository(database_path)
    first_repository.save_backtest_result(BACKTEST_RUN_ID, artifacts.backtest)
    second_repository = SQLiteArtifactRepository(database_path)
    first_load = first_repository.load_backtest_result(BACKTEST_RUN_ID)
    first_load.portfolio.loc[0, "equity"] = 1.0

    second_load = second_repository.load_backtest_result(BACKTEST_RUN_ID)
    assert second_load.portfolio.loc[0, "equity"] != 1.0

    connection = connect_database(database_path)
    try:
        connection.execute(
            """
            UPDATE backtest_source_market_rows
            SET open = open + 1.0
            WHERE backtest_run_id = ? AND sequence_number = 0
            """,
            (BACKTEST_RUN_ID,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PersistenceIntegrityError, match="market data"):
        first_repository.load_backtest_result(BACKTEST_RUN_ID)
