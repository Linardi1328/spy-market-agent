from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from spy_market_agent.config import Settings
from spy_market_agent.execution import (
    DISENGAGE_KILL_SWITCH_CONFIRMATION,
    PAPER_ATTEMPT_ACCEPTED,
    PAPER_ATTEMPT_RESERVED,
    PAPER_ATTEMPT_SUBMISSION_UNKNOWN,
    PaperExecutionDuplicateError,
    PaperExecutionInputError,
    PaperExecutionIntegrityError,
    SQLitePaperExecutionRepository,
)
from spy_market_agent.persistence import initialize_database
from spy_market_agent.persistence.models import PersistenceSchemaError
from spy_market_agent.persistence.schema import (
    PERSISTENCE_SCHEMA_VERSION,
    PERSISTENCE_SCHEMA_VERSION_V1,
)
from unit.phase8_helpers import make_approval, make_instruction, make_receipt


def test_fresh_database_defaults_kill_switch_to_engaged(tmp_path: Path) -> None:
    database_path = tmp_path / "phase8.sqlite3"
    initialize_database(database_path)
    repository = SQLitePaperExecutionRepository(database_path)

    state = repository.get_kill_switch_state()
    status = repository.status(Settings())

    assert state.kill_switch_engaged is True
    assert state.reason == "default_engaged"
    assert status.kill_switch_engaged is True
    assert status.paper_execution_enabled is False
    assert status.dry_run is True


def test_disengaging_kill_switch_requires_confirmation_reason_and_audits(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8.sqlite3"
    initialize_database(database_path)
    repository = SQLitePaperExecutionRepository(database_path)
    now = datetime(2025, 1, 3, 14, 0, tzinfo=UTC)

    with pytest.raises(PaperExecutionInputError):
        repository.set_paper_execution_kill_switch(
            engaged=False,
            reason="explicit_test",
            updated_at_utc=now,
        )

    disengaged = repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_test",
        updated_at_utc=now,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    reengaged = repository.set_paper_execution_kill_switch(
        engaged=True,
        reason="safety_reengaged",
        updated_at_utc=now,
    )
    events = repository.list_events()

    assert disengaged.kill_switch_engaged is False
    assert reengaged.kill_switch_engaged is True
    assert [event.event_type for event in events] == [
        "kill_switch_updated",
        "kill_switch_updated",
    ]
    assert events[0].new_state == "disengaged"
    assert events[1].new_state == "engaged"


def test_attempt_round_trip_and_duplicate_protection_survive_repository_reopen(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8.sqlite3"
    initialize_database(database_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    repository = SQLitePaperExecutionRepository(database_path)

    reserved = repository.reserve_attempt(
        instruction,
        approval,
        execution_risk_approved=True,
        now_utc=instruction.created_at_utc,
    )
    accepted = repository.record_receipt(
        make_receipt(instruction),
        status=PAPER_ATTEMPT_ACCEPTED,
        account_id_fingerprint="a" * 64,
        now_utc=instruction.created_at_utc,
        event_type="broker_order_accepted",
    )

    reopened = SQLitePaperExecutionRepository(database_path)
    loaded = reopened.get_attempt(instruction.client_order_id)
    with pytest.raises(PaperExecutionDuplicateError):
        reopened.reserve_attempt(
            instruction,
            approval,
            execution_risk_approved=True,
            now_utc=instruction.created_at_utc,
        )

    assert reserved.attempt_status == PAPER_ATTEMPT_RESERVED
    assert accepted.attempt_status == PAPER_ATTEMPT_ACCEPTED
    assert loaded.broker_status == "accepted"
    assert reopened.count_attempts() == 1
    assert [
        event.event_type
        for event in reopened.list_events(client_order_id=instruction.client_order_id)
    ] == [
        "attempt_reserved",
        "broker_order_accepted",
    ]


def test_submission_unknown_retains_reservation(tmp_path: Path) -> None:
    database_path = tmp_path / "phase8.sqlite3"
    initialize_database(database_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    repository = SQLitePaperExecutionRepository(database_path)
    repository.reserve_attempt(
        instruction,
        approval,
        execution_risk_approved=True,
        now_utc=instruction.created_at_utc,
    )

    unknown = repository.mark_submission_unknown(
        client_order_id=instruction.client_order_id,
        signal_id=instruction.signal_id,
        failure_code="timeout",
        now_utc=instruction.created_at_utc,
    )

    assert unknown.attempt_status == PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    assert unknown.failure_code == "timeout"
    with pytest.raises(PaperExecutionDuplicateError):
        repository.reserve_attempt(
            instruction,
            approval,
            execution_risk_approved=True,
            now_utc=instruction.created_at_utc,
        )


def test_tampered_attempt_rows_fail_with_project_owned_integrity_error(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8.sqlite3"
    initialize_database(database_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    repository = SQLitePaperExecutionRepository(database_path)
    repository.reserve_attempt(
        instruction,
        approval,
        execution_risk_approved=True,
        now_utc=instruction.created_at_utc,
    )
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "UPDATE paper_execution_attempts SET quantity = ? WHERE client_order_id = ?",
            ("not-an-int", instruction.client_order_id),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PaperExecutionIntegrityError):
        repository.get_attempt(instruction.client_order_id)


def test_corrupted_kill_switch_state_fails_closed(tmp_path: Path) -> None:
    database_path = tmp_path / "phase8.sqlite3"
    initialize_database(database_path)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE paper_execution_control SET kill_switch_engaged = 7 WHERE singleton_id = 1"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PaperExecutionIntegrityError):
        SQLitePaperExecutionRepository(database_path).get_kill_switch_state()


def test_phase7_v1_database_migrates_to_v2_with_engaged_kill_switch(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase7.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")
        connection.execute(
            "INSERT INTO schema_migrations(version) VALUES (?)",
            (PERSISTENCE_SCHEMA_VERSION_V1,),
        )
        connection.commit()
    finally:
        connection.close()

    initialize_database(database_path)
    connection = sqlite3.connect(database_path)
    try:
        versions = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    finally:
        connection.close()
    state = SQLitePaperExecutionRepository(database_path).get_kill_switch_state()

    assert versions == {PERSISTENCE_SCHEMA_VERSION}
    assert state.kill_switch_engaged is True


def test_unsupported_future_schema_is_rejected_without_migration(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT)"
        )
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES ('future', 'now')"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PersistenceSchemaError):
        initialize_database(database_path)
