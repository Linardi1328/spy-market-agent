from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from spy_market_agent.config import Settings
from spy_market_agent.execution import (
    DISENGAGE_KILL_SWITCH_CONFIRMATION,
    PAPER_ATTEMPT_ACCEPTED,
    PAPER_ATTEMPT_BLOCKED,
    PAPER_ATTEMPT_BROKER_EXISTING_ORDER_FOUND,
    PAPER_ATTEMPT_RECONCILED,
    PAPER_ATTEMPT_REJECTED,
    PAPER_ATTEMPT_SUBMISSION_UNKNOWN,
    PaperExecutionBrokerRejectionError,
    PaperExecutionBrokerRequestError,
    PaperExecutionBrokerStateError,
    PaperExecutionConfigurationError,
    PaperExecutionDuplicateError,
    PaperExecutionError,
    PaperExecutionIntegrityError,
    PaperExecutionKillSwitchError,
    PaperExecutionPermissionError,
    PaperExecutionService,
    PaperExecutionStaleSignalError,
    PaperExecutionSubmissionUnknownError,
    SQLitePaperExecutionRepository,
)
from spy_market_agent.execution.models import (
    BrokerAccountConfigurationSnapshot,
    BrokerAccountSnapshot,
    BrokerClockSnapshot,
    BrokerEnvironmentSnapshot,
    BrokerOpenOrderSnapshot,
    BrokerPositionSnapshot,
)
from spy_market_agent.persistence import initialize_database
from spy_market_agent.risk import SELL_SIDE
from unit.phase8_helpers import (
    BROKER_TIME,
    CLIENT_ORDER_ID,
    FakePaperBroker,
    make_approval,
    make_broker_order_snapshot,
    make_instruction,
    make_proposed_order,
)


def _repository(tmp_path: Path) -> SQLitePaperExecutionRepository:
    database_path = tmp_path / "phase8.sqlite3"
    initialize_database(database_path)
    return SQLitePaperExecutionRepository(database_path)


def _enabled_settings() -> Settings:
    return Settings(
        enable_paper_execution=True,
        dry_run=False,
        alpaca_api_key=SecretStr("AKTEST"),
        alpaca_secret_key=SecretStr("SKTEST"),
    )


def _ready_service(tmp_path: Path) -> tuple[PaperExecutionService, SQLitePaperExecutionRepository]:
    repository = _repository(tmp_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_test",
        updated_at_utc=BROKER_TIME,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    return PaperExecutionService(settings=_enabled_settings(), repository=repository), repository


def test_default_settings_and_dry_run_block_submission_without_broker_submit(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker()

    with pytest.raises(PaperExecutionConfigurationError):
        PaperExecutionService(settings=Settings(), repository=repository).submit_approved_order(
            instruction,
            approval,
            broker=broker,
        )

    dry_run_service = PaperExecutionService(
        settings=Settings(enable_paper_execution=True, dry_run=True),
        repository=repository,
    )
    preview = dry_run_service.preview_submission(
        instruction,
        approval,
        now_utc=BROKER_TIME,
    )
    with pytest.raises(PaperExecutionPermissionError):
        dry_run_service.submit_approved_order(instruction, approval, broker=broker)

    assert "dry_run_enabled" in preview.blocked_gate_codes
    assert broker.submit_calls == 0


def test_missing_credentials_block_explicit_submission(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = PaperExecutionService(
        settings=Settings(enable_paper_execution=True, dry_run=False),
        repository=repository,
    )

    with pytest.raises(PaperExecutionConfigurationError, match="Alpaca paper API key"):
        service.submit_approved_order(
            make_instruction(),
            make_approval(make_instruction()),
            broker=FakePaperBroker(),
        )


def test_live_mode_request_at_execution_boundary_raises_runtime_error(
    tmp_path: Path,
) -> None:
    settings = Settings.model_construct(
        execution_mode="live",
        enable_paper_execution=True,
        dry_run=False,
        alpaca_api_key=SecretStr("AKTEST"),
        alpaca_secret_key=SecretStr("SKTEST"),
        paper_execution_require_market_open=True,
    )
    service = PaperExecutionService(settings=settings, repository=_repository(tmp_path))
    instruction = make_instruction()

    with pytest.raises(RuntimeError):
        service.submit_approved_order(
            instruction,
            make_approval(instruction),
            broker=FakePaperBroker(),
        )


def test_kill_switch_blocks_submission_until_explicitly_disengaged(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)
    instruction = make_instruction()
    broker = FakePaperBroker()

    with pytest.raises(PaperExecutionKillSwitchError):
        service.submit_approved_order(instruction, make_approval(instruction), broker=broker)

    assert broker.submit_calls == 0


def test_successful_submission_reserves_ids_records_receipt_and_blocks_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker()
    kill_switch_reads = 0
    real_kill_switch_state = repository.get_kill_switch_state

    def counted_kill_switch_state() -> object:
        nonlocal kill_switch_reads
        kill_switch_reads += 1
        return real_kill_switch_state()

    monkeypatch.setattr(repository, "get_kill_switch_state", counted_kill_switch_state)

    receipt = service.submit_approved_order(instruction, approval, broker=broker)
    second_broker = FakePaperBroker()

    assert receipt.client_order_id == CLIENT_ORDER_ID
    assert broker.submit_calls == 1
    assert kill_switch_reads == 2
    assert repository.get_attempt(CLIENT_ORDER_ID).attempt_status == PAPER_ATTEMPT_ACCEPTED
    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(instruction, approval, broker=second_broker)
    assert second_broker.submit_calls == 0


def test_broker_request_construction_failure_blocks_reserved_attempt(
    tmp_path: Path,
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker(
        submit_error=PaperExecutionBrokerRequestError(
            "broker_request_construction_failed",
            "paper-order request could not be constructed locally.",
        )
    )

    with pytest.raises(PaperExecutionBrokerRequestError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)

    attempt = repository.get_attempt(CLIENT_ORDER_ID)
    events = repository.list_events(client_order_id=CLIENT_ORDER_ID)

    assert "reconciliation" not in str(exc_info.value).lower()
    assert broker.submit_calls == 1
    assert broker.lookup_calls == 1
    assert attempt.attempt_status == PAPER_ATTEMPT_BLOCKED
    assert attempt.failure_code == "broker_request_construction_failed"
    assert [event.event_type for event in events] == [
        "attempt_reserved",
        "broker_request_construction_failed",
    ]
    assert events[-1].signal_id == instruction.signal_id
    assert events[-1].client_order_id == instruction.client_order_id
    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(instruction, approval, broker=FakePaperBroker())


def test_existing_broker_order_is_reconciled_without_second_submission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    snapshot = make_broker_order_snapshot(instruction)
    broker = FakePaperBroker(existing_order=snapshot)
    kill_switch_reads = 0
    real_kill_switch_state = repository.get_kill_switch_state

    def counted_kill_switch_state() -> object:
        nonlocal kill_switch_reads
        kill_switch_reads += 1
        return real_kill_switch_state()

    monkeypatch.setattr(repository, "get_kill_switch_state", counted_kill_switch_state)

    returned = service.submit_approved_order(instruction, approval, broker=broker)

    assert returned.signal_id == instruction.signal_id
    assert returned.instruction_fingerprint == instruction.instruction_fingerprint
    assert broker.submit_calls == 0
    assert broker.lookup_calls == 1
    assert kill_switch_reads == 1
    assert repository.get_attempt(CLIENT_ORDER_ID).attempt_status == (
        PAPER_ATTEMPT_BROKER_EXISTING_ORDER_FOUND
    )


def test_final_kill_switch_reread_blocks_after_reservation_and_keeps_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker()
    real_kill_switch_state = repository.get_kill_switch_state
    kill_switch_reads = 0

    def race_kill_switch_state() -> object:
        nonlocal kill_switch_reads
        kill_switch_reads += 1
        if kill_switch_reads == 2:
            connection = sqlite3.connect(tmp_path / "phase8.sqlite3")
            try:
                connection.execute(
                    """
                    UPDATE paper_execution_control
                    SET kill_switch_engaged = 1, reason = 'race_engaged'
                    WHERE singleton_id = 1
                    """
                )
                connection.commit()
            finally:
                connection.close()
        return real_kill_switch_state()

    monkeypatch.setattr(repository, "get_kill_switch_state", race_kill_switch_state)

    with pytest.raises(PaperExecutionKillSwitchError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)

    attempt = repository.get_attempt(CLIENT_ORDER_ID)
    event_types = [
        event.event_type for event in repository.list_events(client_order_id=CLIENT_ORDER_ID)
    ]

    assert exc_info.value.code == "kill_switch_engaged_before_submission"
    assert broker.submit_calls == 0
    assert broker.lookup_calls == 1
    assert kill_switch_reads == 2
    assert attempt.attempt_status == PAPER_ATTEMPT_BLOCKED
    assert attempt.failure_code == "kill_switch_engaged_before_submission"
    assert event_types == ["attempt_reserved", "final_kill_switch_blocked"]
    with pytest.raises(PaperExecutionDuplicateError):
        repository.reserve_attempt(
            instruction,
            approval,
            execution_risk_approved=True,
            now_utc=BROKER_TIME,
        )


def test_final_kill_switch_read_failure_blocks_submission_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker()
    real_kill_switch_state = repository.get_kill_switch_state
    kill_switch_reads = 0

    def failing_final_kill_switch_state() -> object:
        nonlocal kill_switch_reads
        kill_switch_reads += 1
        if kill_switch_reads == 2:
            raise PaperExecutionIntegrityError(
                "invalid_kill_switch_state",
                "paper-execution kill switch state is invalid and must be treated as engaged.",
            )
        return real_kill_switch_state()

    monkeypatch.setattr(repository, "get_kill_switch_state", failing_final_kill_switch_state)

    with pytest.raises(PaperExecutionKillSwitchError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)

    attempt = repository.get_attempt(CLIENT_ORDER_ID)

    assert exc_info.value.code == "kill_switch_state_unavailable_before_submission"
    assert broker.submit_calls == 0
    assert kill_switch_reads == 2
    assert attempt.attempt_status == PAPER_ATTEMPT_BLOCKED
    assert attempt.failure_code == "kill_switch_state_unavailable_before_submission"


def test_no_broker_operation_occurs_after_final_kill_switch_check_except_submit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker()
    operations: list[str] = []
    broker.operation_log = operations
    real_kill_switch_state = repository.get_kill_switch_state

    def logged_kill_switch_state() -> object:
        operations.append("kill_switch_read")
        return real_kill_switch_state()

    monkeypatch.setattr(repository, "get_kill_switch_state", logged_kill_switch_state)

    service.submit_approved_order(instruction, approval, broker=broker)

    final_read_index = len(operations) - 1 - operations[::-1].index("kill_switch_read")
    assert operations[final_read_index + 1] == "submit_market_day_order"


def test_timeout_marks_submission_unknown_and_reconciliation_never_submits(
    tmp_path: Path,
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker(submit_error=TimeoutError("network timeout with secret"))

    with pytest.raises(PaperExecutionSubmissionUnknownError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)
    assert "secret" not in str(exc_info.value).lower()
    assert broker.submit_calls == 1
    assert repository.get_attempt(CLIENT_ORDER_ID).attempt_status == (
        PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    )

    duplicate_broker = FakePaperBroker()
    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(instruction, approval, broker=duplicate_broker)
    assert duplicate_broker.submit_calls == 0

    reconcile_broker = FakePaperBroker(existing_order=make_broker_order_snapshot(instruction))
    reconciled = service.reconcile_by_client_order_id(
        CLIENT_ORDER_ID,
        broker=reconcile_broker,
        now_utc=BROKER_TIME + timedelta(minutes=1),
    )

    assert reconciled is not None
    assert reconcile_broker.submit_calls == 0
    assert repository.get_attempt(CLIENT_ORDER_ID).attempt_status == PAPER_ATTEMPT_RECONCILED


def test_definitive_broker_rejection_records_rejected_without_retry(tmp_path: Path) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker(
        submit_error=PaperExecutionBrokerRejectionError(
            "broker_order_rejected",
            "paper broker rejected the order.",
        )
    )

    with pytest.raises(PaperExecutionBrokerRejectionError):
        service.submit_approved_order(instruction, approval, broker=broker)

    assert broker.submit_calls == 1
    assert repository.get_attempt(CLIENT_ORDER_ID).attempt_status == PAPER_ATTEMPT_REJECTED
    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(instruction, approval, broker=FakePaperBroker())


@pytest.mark.parametrize(
    "submit_error",
    [
        TimeoutError("raw secret timeout"),
        ConnectionError("raw secret connection loss"),
        RuntimeError("raw secret sdk failure"),
        asyncio.CancelledError("raw secret cancellation"),
    ],
)
def test_uncertain_submit_exceptions_become_submission_unknown(
    tmp_path: Path,
    submit_error: BaseException,
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker(submit_error=submit_error)

    with pytest.raises(PaperExecutionSubmissionUnknownError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)

    assert "secret" not in str(exc_info.value).lower()
    assert broker.submit_calls == 1
    assert repository.get_attempt(CLIENT_ORDER_ID).attempt_status == (
        PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    )
    assert repository.get_attempt(CLIENT_ORDER_ID).attempt_status != PAPER_ATTEMPT_REJECTED
    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(instruction, approval, broker=FakePaperBroker())


@pytest.mark.parametrize(
    "snapshot_change",
    [
        {"broker_order_id": ""},
        {"client_order_id": "other-client-order"},
        {"symbol": "QQQ"},
        {"side": "sell"},
        {"submitted_quantity": 11},
        {"order_type": "limit"},
        {"time_in_force": "gtc"},
        {"extended_hours": True},
    ],
)
def test_post_submit_malformed_or_contradictory_snapshot_is_unknown_not_rejected(
    tmp_path: Path,
    snapshot_change: dict[str, object],
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    snapshot = make_broker_order_snapshot(instruction)
    for field_name, value in snapshot_change.items():
        object.__setattr__(snapshot, field_name, value)
    broker = FakePaperBroker(submit_snapshot=snapshot)

    with pytest.raises(PaperExecutionSubmissionUnknownError):
        service.submit_approved_order(instruction, approval, broker=broker)

    attempt = repository.get_attempt(CLIENT_ORDER_ID)
    assert broker.submit_calls == 1
    assert attempt.attempt_status == PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    assert attempt.failure_code == "broker_snapshot_mismatch"
    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(instruction, approval, broker=FakePaperBroker())


def test_existing_mismatching_broker_order_fails_closed_without_submission(
    tmp_path: Path,
) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    snapshot = replace(make_broker_order_snapshot(instruction), side="sell")
    broker = FakePaperBroker(existing_order=snapshot)

    with pytest.raises(PaperExecutionSubmissionUnknownError):
        service.submit_approved_order(instruction, approval, broker=broker)

    attempt = repository.get_attempt(CLIENT_ORDER_ID)
    events = repository.list_events(client_order_id=CLIENT_ORDER_ID)
    assert broker.submit_calls == 0
    assert attempt.attempt_status == PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    assert events[-1].event_type == "broker_order_mismatch"


def test_reconciliation_rejects_mismatch_and_never_submits(tmp_path: Path) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    repository.reserve_attempt(
        instruction,
        approval,
        execution_risk_approved=True,
        now_utc=BROKER_TIME,
    )
    broker = FakePaperBroker(
        existing_order=replace(make_broker_order_snapshot(instruction), submitted_quantity=1)
    )

    with pytest.raises(PaperExecutionSubmissionUnknownError):
        service.reconcile_by_client_order_id(
            CLIENT_ORDER_ID,
            broker=broker,
            now_utc=BROKER_TIME + timedelta(minutes=1),
        )

    assert broker.submit_calls == 0
    assert repository.get_attempt(CLIENT_ORDER_ID).attempt_status == (
        PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    )


def test_reconciliation_does_not_convert_terminal_attempt(tmp_path: Path) -> None:
    service, repository = _ready_service(tmp_path)
    instruction = make_instruction()
    approval = make_approval(instruction)
    broker = FakePaperBroker()
    service.submit_approved_order(instruction, approval, broker=broker)
    reconcile_broker = FakePaperBroker(existing_order=make_broker_order_snapshot(instruction))

    with pytest.raises(PaperExecutionIntegrityError):
        service.reconcile_by_client_order_id(
            CLIENT_ORDER_ID,
            broker=reconcile_broker,
            now_utc=BROKER_TIME + timedelta(minutes=1),
        )

    assert reconcile_broker.submit_calls == 0
    assert repository.get_attempt(CLIENT_ORDER_ID).attempt_status == PAPER_ATTEMPT_ACCEPTED


@pytest.mark.parametrize(
    ("broker", "error_type", "code"),
    [
        (
            FakePaperBroker(
                environment=BrokerEnvironmentSnapshot(
                    environment_name="alpaca_live",
                    endpoint_identity="https://api.alpaca.markets",
                    is_paper=False,
                    verified_at_utc=BROKER_TIME,
                )
            ),
            PaperExecutionBrokerStateError,
            "unsafe_broker_environment",
        ),
        (
            FakePaperBroker(
                account=BrokerAccountSnapshot(
                    status="INACTIVE",
                    currency="USD",
                    cash=Decimal("10000"),
                    equity=Decimal("10000"),
                    buying_power=Decimal("10000"),
                    trading_blocked=False,
                    account_blocked=False,
                    trade_suspended_by_user=False,
                    account_id_fingerprint="a" * 64,
                    retrieved_at_utc=BROKER_TIME,
                )
            ),
            PaperExecutionBrokerStateError,
            "account_not_active",
        ),
        (
            FakePaperBroker(
                account=BrokerAccountSnapshot(
                    status="active",
                    currency="USD",
                    cash=Decimal("10000"),
                    equity=Decimal("10000"),
                    buying_power=Decimal("10000"),
                    trading_blocked=True,
                    account_blocked=False,
                    trade_suspended_by_user=False,
                    account_id_fingerprint="a" * 64,
                    retrieved_at_utc=BROKER_TIME,
                )
            ),
            PaperExecutionBrokerStateError,
            "account_blocked",
        ),
        (
            FakePaperBroker(
                account_configuration=BrokerAccountConfigurationSnapshot(
                    no_shorting=False,
                    max_margin_multiplier=Decimal("1"),
                    fractional_trading_enabled=False,
                    suspend_trade=False,
                    retrieved_at_utc=BROKER_TIME,
                )
            ),
            PaperExecutionBrokerStateError,
            "shorting_enabled",
        ),
        (
            FakePaperBroker(
                clock=BrokerClockSnapshot(
                    timestamp=BROKER_TIME,
                    is_open=False,
                    next_open=BROKER_TIME + timedelta(days=1),
                    next_close=BROKER_TIME + timedelta(hours=6),
                )
            ),
            PaperExecutionStaleSignalError,
            "market_closed",
        ),
        (
            FakePaperBroker(
                positions=(
                    BrokerPositionSnapshot(
                        symbol="SPY",
                        side="long",
                        quantity=Decimal("1"),
                        available_quantity=Decimal("1"),
                    ),
                )
            ),
            PaperExecutionBrokerStateError,
            "pyramiding_forbidden",
        ),
        (
            FakePaperBroker(
                positions=(
                    BrokerPositionSnapshot(
                        symbol="SPY",
                        side="short",
                        quantity=Decimal("1"),
                        available_quantity=Decimal("1"),
                    ),
                )
            ),
            PaperExecutionBrokerStateError,
            "short_position",
        ),
        (
            FakePaperBroker(
                open_orders=(
                    BrokerOpenOrderSnapshot(
                        broker_order_id="broker-open-1",
                        client_order_id="other-order",
                        symbol="SPY",
                        side="buy",
                        quantity=Decimal("1"),
                        filled_quantity=Decimal("0"),
                        status="accepted",
                        submitted_at_utc=BROKER_TIME,
                    ),
                )
            ),
            PaperExecutionBrokerStateError,
            "conflicting_open_order",
        ),
    ],
)
def test_broker_preflight_failures_block_submission(
    tmp_path: Path,
    broker: FakePaperBroker,
    error_type: type[PaperExecutionError],
    code: str,
) -> None:
    service, _repository = _ready_service(tmp_path)
    instruction = make_instruction()

    with pytest.raises(error_type) as exc_info:
        service.submit_approved_order(
            instruction,
            make_approval(instruction),
            broker=broker,
        )

    assert exc_info.value.code == code
    assert broker.submit_calls == 0


def test_sell_requires_complete_existing_long_position(tmp_path: Path) -> None:
    service, _repository = _ready_service(tmp_path)
    order = make_proposed_order(quantity=10, side=SELL_SIDE)
    instruction = make_instruction(order=order)
    broker = FakePaperBroker(
        positions=(
            BrokerPositionSnapshot(
                symbol="SPY",
                side="long",
                quantity=Decimal("10"),
                available_quantity=Decimal("10"),
            ),
        )
    )

    receipt = service.submit_approved_order(
        instruction,
        make_approval(instruction),
        broker=broker,
    )

    assert receipt.side == SELL_SIDE
    assert broker.submit_calls == 1
