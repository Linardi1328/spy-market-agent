from __future__ import annotations

import sqlite3

from spy_market_agent.persistence.models import PersistenceSchemaError

PERSISTENCE_SCHEMA_VERSION = "spy-sqlite-persistence-v1"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS market_data_batches (
    run_id TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    adjustment_policy TEXT NOT NULL,
    downloaded_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    first_session TEXT NOT NULL,
    last_session TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count > 0),
    dataset_checksum TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_description TEXT
);

CREATE TABLE IF NOT EXISTS market_data_rows (
    batch_run_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    session TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL CHECK (volume >= 0),
    PRIMARY KEY (batch_run_id, sequence_number),
    FOREIGN KEY (batch_run_id) REFERENCES market_data_batches(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_runs (
    run_id TEXT PRIMARY KEY,
    selected_model_name TEXT NOT NULL,
    selection_rule_version TEXT NOT NULL,
    selection_reason TEXT NOT NULL,
    roc_auc_tie_break_required INTEGER NOT NULL CHECK (roc_auc_tie_break_required IN (0, 1)),
    log_loss_tie_break_required INTEGER NOT NULL CHECK (log_loss_tie_break_required IN (0, 1)),
    brier_score_tie_break_required INTEGER NOT NULL
        CHECK (brier_score_tie_break_required IN (0, 1)),
    source_market_data_checksum TEXT NOT NULL,
    source_schema_version TEXT NOT NULL,
    feature_schema_version TEXT NOT NULL,
    label_schema_version TEXT NOT NULL,
    feature_columns_json TEXT NOT NULL,
    split_spec_json TEXT NOT NULL,
    train_row_count INTEGER NOT NULL,
    validation_row_count INTEGER NOT NULL,
    train_first_session TEXT NOT NULL,
    train_last_session TEXT NOT NULL,
    validation_first_session TEXT NOT NULL,
    validation_last_session TEXT NOT NULL,
    test_row_count INTEGER NOT NULL,
    test_first_session TEXT NOT NULL,
    test_last_session TEXT NOT NULL,
    random_seed INTEGER NOT NULL,
    diagnostic_classification_threshold REAL NOT NULL,
    sklearn_version TEXT NOT NULL,
    model_schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    git_commit_hash TEXT,
    python_version TEXT NOT NULL,
    dependency_versions_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_validation_metric_snapshots (
    run_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    model_name TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    positive_count INTEGER NOT NULL,
    negative_count INTEGER NOT NULL,
    log_loss REAL NOT NULL,
    brier_score REAL NOT NULL,
    roc_auc REAL NOT NULL,
    PRIMARY KEY (run_id, sequence_number),
    FOREIGN KEY (run_id) REFERENCES model_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_candidate_parameters (
    run_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    parameter_name TEXT NOT NULL,
    parameter_value_json TEXT NOT NULL,
    PRIMARY KEY (run_id, model_name, sequence_number),
    FOREIGN KEY (run_id) REFERENCES model_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_predictions (
    run_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    session TEXT NOT NULL,
    probability_positive REAL NOT NULL,
    predicted_class INTEGER NOT NULL CHECK (predicted_class IN (0, 1)),
    target INTEGER NOT NULL CHECK (target IN (0, 1)),
    PRIMARY KEY (run_id, sequence_number),
    FOREIGN KEY (run_id) REFERENCES model_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_final_metrics (
    run_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    partition_name TEXT NOT NULL,
    diagnostic_classification_threshold REAL NOT NULL,
    row_count INTEGER NOT NULL,
    positive_count INTEGER NOT NULL,
    negative_count INTEGER NOT NULL,
    positive_rate REAL NOT NULL,
    log_loss REAL NOT NULL,
    brier_score REAL NOT NULL,
    roc_auc REAL NOT NULL,
    average_precision REAL NOT NULL,
    accuracy_at_0_5 REAL NOT NULL,
    precision_at_0_5 REAL NOT NULL,
    recall_at_0_5 REAL NOT NULL,
    f1_at_0_5 REAL NOT NULL,
    true_negative_count INTEGER NOT NULL,
    false_positive_count INTEGER NOT NULL,
    false_negative_count INTEGER NOT NULL,
    true_positive_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES model_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    selected_model_name TEXT NOT NULL,
    source_market_data_checksum TEXT NOT NULL,
    source_schema_version TEXT NOT NULL,
    feature_schema_version TEXT NOT NULL,
    label_schema_version TEXT NOT NULL,
    model_schema_version TEXT NOT NULL,
    strategy_schema_version TEXT NOT NULL,
    risk_schema_version TEXT NOT NULL,
    backtest_schema_version TEXT NOT NULL,
    feature_columns_json TEXT NOT NULL,
    split_spec_json TEXT NOT NULL,
    strategy_threshold REAL NOT NULL,
    first_signal_session TEXT NOT NULL,
    last_signal_session TEXT NOT NULL,
    first_execution_session TEXT NOT NULL,
    last_execution_session TEXT NOT NULL,
    initial_cash TEXT NOT NULL,
    commission_bps_per_side TEXT NOT NULL,
    slippage_bps_per_side TEXT NOT NULL,
    risk_supported_symbol TEXT NOT NULL,
    risk_allow_short_selling INTEGER NOT NULL CHECK (risk_allow_short_selling IN (0, 1)),
    risk_allow_leverage INTEGER NOT NULL CHECK (risk_allow_leverage IN (0, 1)),
    risk_allow_fractional_shares INTEGER NOT NULL CHECK (risk_allow_fractional_shares IN (0, 1)),
    risk_maximum_position_weight REAL NOT NULL,
    sklearn_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    execution_price_checksum TEXT NOT NULL,
    git_commit_hash TEXT,
    python_version TEXT NOT NULL,
    dependency_versions_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_source_market_metadata (
    backtest_run_id TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    adjustment_policy TEXT NOT NULL,
    downloaded_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    first_session TEXT NOT NULL,
    last_session TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count > 0),
    dataset_checksum TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_description TEXT,
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_source_market_rows (
    backtest_run_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    session TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL CHECK (volume >= 0),
    PRIMARY KEY (backtest_run_id, sequence_number),
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_strategy_signals (
    backtest_run_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    signal_session TEXT NOT NULL,
    execution_session TEXT NOT NULL,
    probability_positive REAL NOT NULL,
    target_position INTEGER NOT NULL CHECK (target_position IN (0, 1)),
    PRIMARY KEY (backtest_run_id, sequence_number),
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_execution_prices (
    backtest_run_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    execution_session TEXT NOT NULL,
    reference_open REAL NOT NULL,
    close_price REAL NOT NULL,
    PRIMARY KEY (backtest_run_id, sequence_number),
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_proposed_orders (
    backtest_run_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    signal_session TEXT NOT NULL,
    execution_session TEXT NOT NULL,
    target_position INTEGER NOT NULL,
    reference_open REAL NOT NULL,
    estimated_execution_price REAL NOT NULL,
    estimated_commission REAL NOT NULL,
    estimated_cash_change REAL NOT NULL,
    current_cash REAL NOT NULL,
    current_shares INTEGER NOT NULL,
    PRIMARY KEY (backtest_run_id, sequence_number),
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_risk_decisions (
    backtest_run_id TEXT NOT NULL,
    order_sequence_number INTEGER NOT NULL,
    approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
    reason_codes_json TEXT NOT NULL,
    evaluated_session TEXT NOT NULL,
    projected_cash REAL NOT NULL,
    projected_shares INTEGER NOT NULL,
    projected_market_value REAL NOT NULL,
    projected_equity REAL NOT NULL,
    PRIMARY KEY (backtest_run_id, order_sequence_number),
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (backtest_run_id, order_sequence_number)
        REFERENCES backtest_proposed_orders(backtest_run_id, sequence_number) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_fills (
    backtest_run_id TEXT NOT NULL,
    order_sequence_number INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    signal_session TEXT NOT NULL,
    execution_session TEXT NOT NULL,
    reference_open REAL NOT NULL,
    execution_price REAL NOT NULL,
    reference_notional REAL NOT NULL,
    execution_notional REAL NOT NULL,
    commission REAL NOT NULL,
    slippage_cost REAL NOT NULL,
    total_transaction_cost REAL NOT NULL,
    cash_change REAL NOT NULL,
    shares_before INTEGER NOT NULL,
    shares_after INTEGER NOT NULL,
    cash_before REAL NOT NULL,
    cash_after REAL NOT NULL,
    risk_approved INTEGER NOT NULL CHECK (risk_approved IN (0, 1)),
    PRIMARY KEY (backtest_run_id, order_sequence_number),
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (backtest_run_id, order_sequence_number)
        REFERENCES backtest_risk_decisions(backtest_run_id, order_sequence_number)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_portfolio_rows (
    backtest_run_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    session TEXT NOT NULL,
    signal_session TEXT NOT NULL,
    target_position INTEGER NOT NULL CHECK (target_position IN (0, 1)),
    cash REAL NOT NULL,
    shares INTEGER NOT NULL,
    close_price REAL NOT NULL,
    market_value REAL NOT NULL,
    equity REAL NOT NULL,
    daily_return REAL NOT NULL,
    drawdown REAL NOT NULL,
    PRIMARY KEY (backtest_run_id, sequence_number),
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_metrics (
    backtest_run_id TEXT PRIMARY KEY,
    session_count INTEGER NOT NULL,
    initial_cash REAL NOT NULL,
    final_cash REAL NOT NULL,
    final_shares INTEGER NOT NULL,
    final_market_value REAL NOT NULL,
    final_equity REAL NOT NULL,
    total_return REAL NOT NULL,
    maximum_drawdown REAL NOT NULL,
    total_reference_notional REAL NOT NULL,
    total_execution_notional REAL NOT NULL,
    total_commission REAL NOT NULL,
    total_slippage_cost REAL NOT NULL,
    total_transaction_cost REAL NOT NULL,
    turnover_ratio REAL NOT NULL,
    exposure_fraction REAL NOT NULL,
    proposed_order_count INTEGER NOT NULL,
    approved_order_count INTEGER NOT NULL,
    rejected_order_count INTEGER NOT NULL,
    fill_count INTEGER NOT NULL,
    buy_fill_count INTEGER NOT NULL,
    sell_fill_count INTEGER NOT NULL,
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE
);
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _reject_unsupported_versions(connection)
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
        (PERSISTENCE_SCHEMA_VERSION,),
    )


def validate_schema_version(connection: sqlite3.Connection) -> None:
    try:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    except sqlite3.Error as exc:
        raise PersistenceSchemaError(
            "missing_schema_version",
            "database has not been explicitly initialized.",
        ) from exc
    if not rows:
        raise PersistenceSchemaError(
            "missing_schema_version",
            "database has not been explicitly initialized.",
        )
    _reject_unsupported_versions(connection)


def _reject_unsupported_versions(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    versions = {str(row[0]) for row in rows}
    unsupported = versions - {PERSISTENCE_SCHEMA_VERSION}
    if unsupported:
        raise PersistenceSchemaError(
            "unsupported_schema_version",
            "database schema version is newer or unsupported by this application.",
        )


__all__ = [
    "PERSISTENCE_SCHEMA_VERSION",
    "initialize_schema",
    "validate_schema_version",
]
