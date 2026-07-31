from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from spy_market_agent.config import Settings
from spy_market_agent.execution import (
    DISENGAGE_KILL_SWITCH_CONFIRMATION,
    PAPER_ATTEMPT_ACCEPTED,
    PAPER_ATTEMPT_BLOCKED,
    PAPER_ATTEMPT_BROKER_EXISTING_ORDER_FOUND,
    PAPER_ATTEMPT_RECONCILED,
    PAPER_ATTEMPT_REJECTED,
    PAPER_ATTEMPT_RESERVED,
    PAPER_ATTEMPT_SUBMISSION_UNKNOWN,
    PaperExecutionDuplicateError,
    PaperExecutionInputError,
    PaperExecutionIntegrityError,
    PaperOrderInstruction,
    PaperOrderReceipt,
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


@pytest.mark.parametrize(
    "receipt_change",
    [
        {"signal_id": "other-signal"},
        {"instruction_fingerprint": "b" * 64},
        {"client_order_id": "other-client-order"},
        {"symbol": "QQQ"},
        {"side": "sell"},
        {"submitted_quantity": 11},
        {"order_type": "limit"},
        {"time_in_force": "gtc"},
        {"extended_hours": True},
    ],
)
def test_record_receipt_rejects_forged_or_mismatched_lineage_transactionally(
    tmp_path: Path,
    receipt_change: dict[str, object],
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
    forged = _forged_receipt(instruction, **receipt_change)

    with pytest.raises(PaperExecutionIntegrityError):
        repository.record_receipt(
            forged,
            status=PAPER_ATTEMPT_ACCEPTED,
            account_id_fingerprint="a" * 64,
            now_utc=instruction.created_at_utc,
            event_type="broker_order_accepted",
        )

    attempt = repository.get_attempt(instruction.client_order_id)
    events = repository.list_events(client_order_id=instruction.client_order_id)
    assert attempt.attempt_status == PAPER_ATTEMPT_RESERVED
    assert attempt.broker_order_id is None
    assert [event.event_type for event in events] == ["attempt_reserved"]


def test_record_receipt_rejects_invalid_state_transition_after_reopen(
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
    repository.mark_failure(
        client_order_id=instruction.client_order_id,
        signal_id=instruction.signal_id,
        status="blocked",
        failure_code="final_kill_switch_blocked",
        now_utc=instruction.created_at_utc,
    )
    reopened = SQLitePaperExecutionRepository(database_path)

    with pytest.raises(PaperExecutionIntegrityError):
        reopened.record_receipt(
            make_receipt(instruction),
            status=PAPER_ATTEMPT_RECONCILED,
            account_id_fingerprint="a" * 64,
            now_utc=instruction.created_at_utc,
            event_type="broker_order_reconciled",
        )

    assert reopened.get_attempt(instruction.client_order_id).attempt_status == "blocked"
    assert [
        event.event_type
        for event in reopened.list_events(client_order_id=instruction.client_order_id)
    ] == [
        "attempt_reserved",
        "attempt_failed",
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


def test_submission_unknown_transition_allows_reserved_and_same_state(
    tmp_path: Path,
) -> None:
    repository, instruction, _approval = _repository_with_reserved_attempt(tmp_path)

    first = repository.mark_submission_unknown(
        client_order_id=instruction.client_order_id,
        signal_id=instruction.signal_id,
        failure_code="timeout",
        now_utc=instruction.created_at_utc,
    )
    second = repository.mark_submission_unknown(
        client_order_id=instruction.client_order_id,
        signal_id=instruction.signal_id,
        failure_code="broker_order_mismatch",
        now_utc=instruction.created_at_utc,
        event_type="broker_order_mismatch",
    )
    events = repository.list_events(client_order_id=instruction.client_order_id)

    assert first.attempt_status == PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    assert second.attempt_status == PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    assert second.failure_code == "broker_order_mismatch"
    assert [event.event_type for event in events] == [
        "attempt_reserved",
        "submission_unknown",
        "broker_order_mismatch",
    ]
    assert events[-1].signal_id == instruction.signal_id
    assert events[-1].client_order_id == instruction.client_order_id


@pytest.mark.parametrize(
    "terminal_status",
    [
        PAPER_ATTEMPT_ACCEPTED,
        PAPER_ATTEMPT_BROKER_EXISTING_ORDER_FOUND,
        PAPER_ATTEMPT_RECONCILED,
        PAPER_ATTEMPT_REJECTED,
        PAPER_ATTEMPT_BLOCKED,
    ],
)
def test_submission_unknown_rejects_terminal_state_regression(
    tmp_path: Path,
    terminal_status: str,
) -> None:
    repository, instruction, _approval = _repository_with_reserved_attempt(tmp_path)
    _move_attempt_to_status(repository, instruction, terminal_status)
    before_attempt = repository.get_attempt(instruction.client_order_id)
    before_events = repository.list_events(client_order_id=instruction.client_order_id)

    with pytest.raises(PaperExecutionIntegrityError):
        repository.mark_submission_unknown(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            failure_code="late_unknown",
            now_utc=instruction.created_at_utc,
        )

    assert repository.get_attempt(instruction.client_order_id) == before_attempt
    assert repository.list_events(client_order_id=instruction.client_order_id) == before_events


@pytest.mark.parametrize("target_status", [PAPER_ATTEMPT_BLOCKED, PAPER_ATTEMPT_REJECTED])
def test_failure_transition_allows_reserved_to_blocked_or_rejected(
    tmp_path: Path,
    target_status: str,
) -> None:
    repository, instruction, _approval = _repository_with_reserved_attempt(tmp_path)

    failed = repository.mark_failure(
        client_order_id=instruction.client_order_id,
        signal_id=instruction.signal_id,
        status=target_status,
        failure_code=f"{target_status}_reason",
        now_utc=instruction.created_at_utc,
    )
    events = repository.list_events(client_order_id=instruction.client_order_id)

    assert failed.attempt_status == target_status
    assert events[-1].signal_id == instruction.signal_id
    assert events[-1].client_order_id == instruction.client_order_id


@pytest.mark.parametrize(
    "target_status",
    [
        PAPER_ATTEMPT_RESERVED,
        PAPER_ATTEMPT_ACCEPTED,
        PAPER_ATTEMPT_BROKER_EXISTING_ORDER_FOUND,
        PAPER_ATTEMPT_SUBMISSION_UNKNOWN,
        PAPER_ATTEMPT_RECONCILED,
    ],
)
def test_failure_transition_rejects_unsupported_target_states(
    tmp_path: Path,
    target_status: str,
) -> None:
    repository, instruction, _approval = _repository_with_reserved_attempt(tmp_path)

    with pytest.raises(PaperExecutionInputError):
        repository.mark_failure(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            status=target_status,
            failure_code="invalid_target",
            now_utc=instruction.created_at_utc,
        )

    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_RESERVED
    )
    assert len(repository.list_events(client_order_id=instruction.client_order_id)) == 1


@pytest.mark.parametrize(
    "terminal_status",
    [
        PAPER_ATTEMPT_ACCEPTED,
        PAPER_ATTEMPT_BROKER_EXISTING_ORDER_FOUND,
        PAPER_ATTEMPT_RECONCILED,
        PAPER_ATTEMPT_REJECTED,
        PAPER_ATTEMPT_BLOCKED,
    ],
)
def test_failure_transition_rejects_terminal_state_regression(
    tmp_path: Path,
    terminal_status: str,
) -> None:
    repository, instruction, _approval = _repository_with_reserved_attempt(tmp_path)
    _move_attempt_to_status(repository, instruction, terminal_status)
    before_attempt = repository.get_attempt(instruction.client_order_id)
    before_events = repository.list_events(client_order_id=instruction.client_order_id)

    with pytest.raises(PaperExecutionIntegrityError):
        repository.mark_failure(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            status=PAPER_ATTEMPT_BLOCKED,
            failure_code="late_block",
            now_utc=instruction.created_at_utc,
        )

    assert repository.get_attempt(instruction.client_order_id) == before_attempt
    assert repository.list_events(client_order_id=instruction.client_order_id) == before_events


def test_wrong_signal_lineage_rejected_by_unknown_and_failure_updates(
    tmp_path: Path,
) -> None:
    repository, instruction, _approval = _repository_with_reserved_attempt(tmp_path)
    before_attempt = repository.get_attempt(instruction.client_order_id)
    before_events = repository.list_events(client_order_id=instruction.client_order_id)

    with pytest.raises(PaperExecutionIntegrityError):
        repository.mark_submission_unknown(
            client_order_id=instruction.client_order_id,
            signal_id="other-signal",
            failure_code="timeout",
            now_utc=instruction.created_at_utc,
        )
    with pytest.raises(PaperExecutionIntegrityError):
        repository.mark_failure(
            client_order_id=instruction.client_order_id,
            signal_id="other-signal",
            status=PAPER_ATTEMPT_BLOCKED,
            failure_code="blocked",
            now_utc=instruction.created_at_utc,
        )

    assert repository.get_attempt(instruction.client_order_id) == before_attempt
    assert repository.list_events(client_order_id=instruction.client_order_id) == before_events


def test_update_row_count_mismatch_is_rejected_transactionally(tmp_path: Path) -> None:
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
    before_attempt = repository.get_attempt(instruction.client_order_id)
    before_events = repository.list_events(client_order_id=instruction.client_order_id)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TRIGGER skip_paper_attempt_update
            BEFORE UPDATE ON paper_execution_attempts
            BEGIN
                SELECT RAISE(IGNORE);
            END
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PaperExecutionIntegrityError):
        repository.mark_submission_unknown(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            failure_code="timeout",
            now_utc=instruction.created_at_utc,
        )

    assert repository.get_attempt(instruction.client_order_id) == before_attempt
    assert repository.list_events(client_order_id=instruction.client_order_id) == before_events


def test_sqlite_failure_rolls_back_attempt_update_and_event_append(tmp_path: Path) -> None:
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
    before_attempt = repository.get_attempt(instruction.client_order_id)
    before_events = repository.list_events(client_order_id=instruction.client_order_id)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TRIGGER fail_submission_unknown_event
            BEFORE INSERT ON paper_execution_events
            WHEN NEW.event_type = 'submission_unknown'
            BEGIN
                SELECT RAISE(FAIL, 'raw sqlite failure with secret text');
            END
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PaperExecutionIntegrityError) as exc_info:
        repository.mark_submission_unknown(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            failure_code="timeout",
            now_utc=instruction.created_at_utc,
        )

    assert "secret" not in str(exc_info.value).lower()
    assert repository.get_attempt(instruction.client_order_id) == before_attempt
    assert repository.list_events(client_order_id=instruction.client_order_id) == before_events


def test_receipt_environment_must_be_alpaca_paper(tmp_path: Path) -> None:
    repository, instruction, _approval = _repository_with_reserved_attempt(tmp_path)
    accepted = repository.record_receipt(
        make_receipt(instruction),
        status=PAPER_ATTEMPT_ACCEPTED,
        account_id_fingerprint="a" * 64,
        now_utc=instruction.created_at_utc,
        event_type="broker_order_accepted",
    )

    assert accepted.broker_environment == "alpaca_paper"


@pytest.mark.parametrize("environment", ["alpaca_live", "live", "production", "paper", "unknown"])
def test_forged_receipt_environment_is_rejected_transactionally(
    tmp_path: Path,
    environment: str,
) -> None:
    repository, instruction, _approval = _repository_with_reserved_attempt(tmp_path)
    before_attempt = repository.get_attempt(instruction.client_order_id)
    before_events = repository.list_events(client_order_id=instruction.client_order_id)
    forged = _forged_receipt(instruction, execution_environment=environment)

    with pytest.raises(PaperExecutionIntegrityError) as exc_info:
        repository.record_receipt(
            forged,
            status=PAPER_ATTEMPT_ACCEPTED,
            account_id_fingerprint="a" * 64,
            now_utc=instruction.created_at_utc,
            event_type="broker_order_accepted",
        )

    assert exc_info.value.code == "receipt_environment_mismatch"
    assert repository.get_attempt(instruction.client_order_id) == before_attempt
    assert repository.list_events(client_order_id=instruction.client_order_id) == before_events
    reopened = SQLitePaperExecutionRepository(tmp_path / "phase8.sqlite3")
    assert reopened.get_attempt(instruction.client_order_id) == before_attempt


def test_blank_receipt_environment_is_rejected_by_model_validation() -> None:
    instruction = make_instruction()

    with pytest.raises(PaperExecutionInputError):
        replace(make_receipt(instruction), execution_environment="")


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


def _forged_receipt(
    instruction: PaperOrderInstruction,
    **changes: object,
) -> PaperOrderReceipt:
    receipt = make_receipt(instruction)
    for field_name, value in changes.items():
        object.__setattr__(receipt, field_name, value)
    return receipt


def _repository_with_reserved_attempt(
    tmp_path: Path,
) -> tuple[SQLitePaperExecutionRepository, PaperOrderInstruction, object]:
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
    return repository, instruction, approval


def _move_attempt_to_status(
    repository: SQLitePaperExecutionRepository,
    instruction: PaperOrderInstruction,
    status: str,
) -> None:
    if status == PAPER_ATTEMPT_RESERVED:
        return
    if status == PAPER_ATTEMPT_SUBMISSION_UNKNOWN:
        repository.mark_submission_unknown(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            failure_code="submission_unknown",
            now_utc=instruction.created_at_utc,
        )
        return
    if status in {PAPER_ATTEMPT_ACCEPTED, PAPER_ATTEMPT_BROKER_EXISTING_ORDER_FOUND}:
        repository.record_receipt(
            make_receipt(instruction),
            status=status,
            account_id_fingerprint="a" * 64,
            now_utc=instruction.created_at_utc,
            event_type=f"{status}_event",
        )
        return
    if status == PAPER_ATTEMPT_RECONCILED:
        repository.mark_submission_unknown(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            failure_code="timeout",
            now_utc=instruction.created_at_utc,
        )
        repository.record_receipt(
            make_receipt(instruction),
            status=PAPER_ATTEMPT_RECONCILED,
            account_id_fingerprint="a" * 64,
            now_utc=instruction.created_at_utc,
            event_type="broker_order_reconciled",
        )
        return
    if status in {PAPER_ATTEMPT_BLOCKED, PAPER_ATTEMPT_REJECTED}:
        repository.mark_failure(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            status=status,
            failure_code=f"{status}_reason",
            now_utc=instruction.created_at_utc,
        )
        return
    raise AssertionError(f"unsupported test status {status}")
