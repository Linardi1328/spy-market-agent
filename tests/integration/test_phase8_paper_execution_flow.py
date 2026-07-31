from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import pytest
from alpaca.trading.enums import (
    AccountStatus,
    AssetClass,
    AssetStatus,
    OrderStatus,
    OrderType,
    PositionSide,
    TimeInForce,
)
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from fastapi.testclient import TestClient
from pydantic import SecretStr

import spy_market_agent.execution.alpaca_paper as alpaca_paper
from spy_market_agent.api import create_app
from spy_market_agent.backtesting import BacktestCostAssumptions, estimate_order_cost
from spy_market_agent.config import Settings
from spy_market_agent.dashboard.app import load_dashboard_state
from spy_market_agent.execution import (
    DISENGAGE_KILL_SWITCH_CONFIRMATION,
    PAPER_ATTEMPT_ACCEPTED,
    PAPER_ATTEMPT_BLOCKED,
    PAPER_ATTEMPT_BROKER_EXISTING_ORDER_FOUND,
    PAPER_ATTEMPT_RECONCILED,
    PAPER_ATTEMPT_RESERVED,
    PAPER_ATTEMPT_SUBMISSION_UNKNOWN,
    PaperExecutionBrokerRequestError,
    PaperExecutionDuplicateError,
    PaperExecutionIntegrityError,
    PaperExecutionKillSwitchError,
    PaperExecutionService,
    PaperExecutionStaleSignalError,
    PaperExecutionSubmissionUnknownError,
    SQLitePaperExecutionRepository,
    build_paper_order_instruction,
)
from spy_market_agent.execution.models import (
    BrokerAccountSnapshot,
    BrokerClockSnapshot,
    PaperOrderApproval,
    PaperOrderInstruction,
    PaperOrderReceipt,
)
from spy_market_agent.risk import (
    BUY_SIDE,
    PortfolioState,
    ProposedOrder,
    RiskConfig,
    RiskDecision,
    evaluate_order_risk,
)
from unit.phase7_helpers import persist_phase7_artifacts
from unit.phase8_helpers import (
    FakePaperBroker,
    make_approval,
    make_broker_order_snapshot,
    make_receipt,
)

NEW_YORK = ZoneInfo("America/New_York")


class ApiClientAdapter:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def health(self) -> dict[str, Any]:
        return self._json("/health")

    def data_status(self) -> dict[str, Any]:
        return self._json("/api/v1/data/status")

    def model_runs(self) -> dict[str, Any]:
        return self._json("/api/v1/model-runs")

    def model_run_detail(self, run_id: str) -> dict[str, Any]:
        return self._json(f"/api/v1/model-runs/{run_id}")

    def model_predictions(
        self,
        run_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._json(
            f"/api/v1/model-runs/{run_id}/predictions",
            params={"limit": limit, "offset": offset},
        )

    def backtests(self) -> dict[str, Any]:
        return self._json("/api/v1/backtests")

    def backtest_detail(self, run_id: str) -> dict[str, Any]:
        return self._json(f"/api/v1/backtests/{run_id}")

    def equity(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]:
        return self._json(
            f"/api/v1/backtests/{run_id}/equity",
            params={"limit": limit, "offset": offset},
        )

    def orders(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]:
        return self._json(
            f"/api/v1/backtests/{run_id}/orders",
            params={"limit": limit, "offset": offset},
        )

    def risk_decisions(
        self,
        run_id: str,
        *,
        limit: int = 250,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._json(
            f"/api/v1/backtests/{run_id}/risk-decisions",
            params={"limit": limit, "offset": offset},
        )

    def fills(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]:
        return self._json(
            f"/api/v1/backtests/{run_id}/fills",
            params={"limit": limit, "offset": offset},
        )

    def paper_trading_status(self) -> dict[str, Any]:
        return self._json("/api/v1/paper-trading/status")

    def paper_orders(self, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return self._json(
            "/api/v1/paper-orders",
            params={"limit": limit, "offset": offset},
        )

    def _json(self, path: str, *, params: dict[str, int] | None = None) -> dict[str, Any]:
        response = self._client.get(path, params=params)
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, dict)
        return payload


class _NotFound(Exception):
    status_code = 404


class EnumBackedTradingClient:
    constructed: ClassVar[list[dict[str, Any]]] = []
    last_instance: ClassVar[EnumBackedTradingClient | None] = None
    clock_time: ClassVar[datetime] = datetime(2025, 1, 3, 15, 30, tzinfo=UTC)

    def __init__(self, **kwargs: Any) -> None:
        EnumBackedTradingClient.constructed.append(kwargs)
        EnumBackedTradingClient.last_instance = self
        self.submit_calls = 0
        self.lookup_calls = 0

    def get_account(self) -> object:
        return type(
            "Account",
            (),
            {
                "status": AccountStatus.ACTIVE,
                "currency": "USD",
                "cash": "10000",
                "equity": "10000",
                "buying_power": "10000",
                "trading_blocked": False,
                "account_blocked": False,
                "trade_suspended_by_user": False,
                "id": "full-account-id",
            },
        )()

    def get_account_configurations(self) -> object:
        return type(
            "Configuration",
            (),
            {
                "no_shorting": True,
                "max_margin_multiplier": "1",
                "fractional_trading": False,
                "suspend_trade": False,
            },
        )()

    def get_clock(self) -> object:
        return type(
            "Clock",
            (),
            {
                "timestamp": self.clock_time,
                "is_open": True,
                "next_open": self.clock_time + timedelta(days=1),
                "next_close": self.clock_time + timedelta(hours=5),
            },
        )()

    def get_asset(self, symbol: str) -> object:
        assert symbol == "SPY"
        return type(
            "Asset",
            (),
            {
                "symbol": "SPY",
                "status": AssetStatus.ACTIVE,
                "tradable": True,
                "fractionable": False,
                "asset_class": AssetClass.US_EQUITY,
            },
        )()

    def get_all_positions(self) -> list[object]:
        return [
            type(
                "Position",
                (),
                {
                    "symbol": "SPY",
                    "side": PositionSide.LONG,
                    "qty": "0",
                    "qty_available": "0",
                    "current_price": "100",
                },
            )()
        ]

    def get_orders(self, *, filter: object) -> list[object]:
        assert filter
        return []

    def get_order_by_client_id(self, client_id: str) -> object:
        assert client_id
        self.lookup_calls += 1
        raise _NotFound()

    def submit_order(self, *, order_data: Any) -> object:
        self.submit_calls += 1
        return type(
            "Order",
            (),
            {
                "id": "enum-backed-paper-order",
                "client_order_id": order_data.client_order_id,
                "symbol": "SPY",
                "side": AlpacaOrderSide.BUY,
                "qty": str(order_data.qty),
                "filled_qty": "0",
                "status": OrderStatus.ACCEPTED,
                "type": OrderType.MARKET,
                "time_in_force": TimeInForce.DAY,
                "extended_hours": False,
                "submitted_at": self.clock_time,
                "updated_at": self.clock_time,
            },
        )()


def _last_enum_client() -> EnumBackedTradingClient:
    client = EnumBackedTradingClient.last_instance
    if client is None:
        raise AssertionError("expected enum-backed trading client to be constructed")
    return client


def test_phase8_paper_execution_flow_is_explicit_auditable_and_duplicate_safe(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-flow",
        client_order_id="paper-order-phase8-flow",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-flow",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    fake_broker = _safe_broker(order, broker_time)

    assert repository.get_kill_switch_state().kill_switch_engaged is True
    with pytest.raises(PaperExecutionKillSwitchError):
        PaperExecutionService(settings=Settings(), repository=repository).submit_approved_order(
            instruction,
            approval,
            broker=fake_broker,
        )
    dry_run = PaperExecutionService(
        settings=Settings(
            enable_paper_execution=True,
            dry_run=True,
            paper_execution_kill_switch=False,
        ),
        repository=repository,
    ).preview_submission(instruction, approval, now_utc=broker_time)
    assert "dry_run_enabled" in dry_run.blocked_gate_codes
    assert fake_broker.submit_calls == 0

    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_integration",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)
    receipt = service.submit_approved_order(instruction, approval, broker=fake_broker)

    assert receipt.symbol == "SPY"
    assert receipt.time_in_force == "day"
    assert fake_broker.submit_calls == 1
    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_ACCEPTED
    )
    assert [
        event.event_type
        for event in repository.list_events(client_order_id=instruction.client_order_id)
    ] == [
        "attempt_reserved",
        "broker_order_accepted",
    ]

    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(
            instruction,
            approval,
            broker=_safe_broker(order, broker_time),
        )
    reopened_repository = SQLitePaperExecutionRepository(database_path)
    with pytest.raises(PaperExecutionDuplicateError):
        PaperExecutionService(
            settings=_enabled_settings(),
            repository=reopened_repository,
        ).submit_approved_order(instruction, approval, broker=_safe_broker(order, broker_time))

    client = TestClient(create_app(database_path=str(database_path), settings=_enabled_settings()))
    status = client.get("/api/v1/paper-trading/status").json()
    history = client.get("/api/v1/paper-orders").json()
    detail = client.get(f"/api/v1/paper-orders/{instruction.client_order_id}").json()
    dashboard_state = load_dashboard_state(ApiClientAdapter(client))

    assert status["kill_switch_engaged"] is False
    assert status["configuration_kill_switch_engaged"] is False
    assert status["durable_kill_switch_engaged"] is False
    assert status["effective_kill_switch_engaged"] is False
    assert status["alpaca_api_key_present"] is True
    assert history["total"] == 1
    assert detail["attempt_status"] == PAPER_ATTEMPT_ACCEPTED
    assert dashboard_state.api_available is True
    assert dashboard_state.paper_trading_status is not None
    assert dashboard_state.paper_order_rows.total == 1
    assert fake_broker.submit_calls == 1
    _assert_credentials_not_persisted(database_path)


def test_phase8_real_sdk_enum_adapter_flow_submits_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "phase8-enum-adapter.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-enum",
        client_order_id="paper-order-phase8-enum",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-enum",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_enum",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    EnumBackedTradingClient.constructed = []
    EnumBackedTradingClient.last_instance = None
    EnumBackedTradingClient.clock_time = broker_time
    monkeypatch.setattr(alpaca_paper, "TradingClient", EnumBackedTradingClient)
    broker = alpaca_paper.AlpacaPaperBroker(api_key="AKPHASE8TEST", secret_key="SKPHASE8TEST")
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)

    receipt = service.submit_approved_order(instruction, approval, broker=broker)

    assert receipt.client_order_id == instruction.client_order_id
    assert receipt.execution_environment == "alpaca_paper"
    assert EnumBackedTradingClient.constructed == [
        {"api_key": "AKPHASE8TEST", "secret_key": "SKPHASE8TEST", "paper": True}
    ]
    enum_client = _last_enum_client()
    assert enum_client.lookup_calls == 1
    assert enum_client.submit_calls == 1
    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_ACCEPTED
    )
    _assert_credentials_not_persisted(database_path)


def test_phase8_local_request_construction_failure_blocks_without_sdk_submit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "phase8-request-build.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-request-build",
        client_order_id="paper-order-phase8-request-build",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-request-build",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_request_build",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    EnumBackedTradingClient.constructed = []
    EnumBackedTradingClient.last_instance = None
    EnumBackedTradingClient.clock_time = broker_time
    monkeypatch.setattr(alpaca_paper, "TradingClient", EnumBackedTradingClient)

    class FailingMarketOrderRequest:
        def __init__(self, **_: object) -> None:
            raise ValueError("raw request model validation secret")

    monkeypatch.setattr(alpaca_paper, "MarketOrderRequest", FailingMarketOrderRequest)
    broker = alpaca_paper.AlpacaPaperBroker(api_key="AKPHASE8TEST", secret_key="SKPHASE8TEST")
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)

    with pytest.raises(PaperExecutionBrokerRequestError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)

    assert "secret" not in str(exc_info.value).lower()
    enum_client = _last_enum_client()
    assert enum_client.lookup_calls == 1
    assert enum_client.submit_calls == 0
    attempt = repository.get_attempt(instruction.client_order_id)
    assert attempt.attempt_status == PAPER_ATTEMPT_BLOCKED
    assert attempt.failure_code == "broker_request_construction_failed"
    assert attempt.attempt_status != PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(
            instruction,
            approval,
            broker=_safe_broker(order, broker_time),
        )


def test_phase8_uncertain_submission_reconciles_without_resubmission(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8-unknown.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-timeout",
        client_order_id="paper-order-phase8-timeout",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-timeout",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_timeout",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    broker = _safe_broker(order, broker_time)
    broker.submit_error = TimeoutError("raw timeout after possible broker receipt")
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)

    with pytest.raises(PaperExecutionSubmissionUnknownError):
        service.submit_approved_order(instruction, approval, broker=broker)
    assert broker.submit_calls == 1
    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    )

    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(
            instruction, approval, broker=_safe_broker(order, broker_time)
        )

    reconcile_broker = _safe_broker(order, broker_time)
    reconcile_broker.existing_order = make_broker_order_snapshot(instruction)
    reconciled = service.reconcile_by_client_order_id(
        instruction.client_order_id,
        broker=reconcile_broker,
        now_utc=broker_time + timedelta(minutes=1),
    )

    assert reconciled is not None
    assert broker.submit_calls == 1
    assert reconcile_broker.submit_calls == 0
    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_RECONCILED
    )
    _assert_credentials_not_persisted(database_path)


def test_phase8_final_kill_switch_race_blocks_after_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "phase8-kill-race.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-kill-race",
        client_order_id="paper-order-phase8-kill-race",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-kill-race",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_kill_race",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)
    broker = _safe_broker(order, broker_time)
    real_kill_switch_state = repository.get_kill_switch_state
    kill_switch_reads = 0

    def race_kill_switch_state() -> object:
        nonlocal kill_switch_reads
        kill_switch_reads += 1
        if kill_switch_reads == 2:
            connection = sqlite3.connect(database_path)
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

    with pytest.raises(PaperExecutionKillSwitchError):
        service.submit_approved_order(instruction, approval, broker=broker)

    attempt = repository.get_attempt(instruction.client_order_id)
    assert broker.submit_calls == 0
    assert attempt.attempt_status == PAPER_ATTEMPT_BLOCKED
    assert attempt.failure_code == "kill_switch_engaged_before_submission"
    with pytest.raises(PaperExecutionDuplicateError):
        repository.reserve_attempt(
            instruction,
            approval,
            execution_risk_approved=True,
            now_utc=broker_time,
        )


def test_phase8_malformed_post_submit_response_is_unknown_and_not_retried(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8-malformed-submit.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-malformed",
        client_order_id="paper-order-phase8-malformed",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-malformed",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_malformed",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    broker = _safe_broker(order, broker_time)
    broker.submit_snapshot = make_broker_order_snapshot(instruction)
    object.__setattr__(broker.submit_snapshot, "symbol", "QQQ")
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)

    with pytest.raises(PaperExecutionSubmissionUnknownError):
        service.submit_approved_order(instruction, approval, broker=broker)

    assert broker.submit_calls == 1
    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    )
    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(
            instruction,
            approval,
            broker=_safe_broker(order, broker_time),
        )
    reconcile_broker = _safe_broker(order, broker_time)
    reconcile_broker.existing_order = make_broker_order_snapshot(instruction)
    reconciled = service.reconcile_by_client_order_id(
        instruction.client_order_id,
        broker=reconcile_broker,
        now_utc=broker_time + timedelta(minutes=1),
    )
    assert reconciled is not None
    assert reconcile_broker.submit_calls == 0
    assert broker.submit_calls == 1


def test_phase8_existing_broker_order_lineage_and_mismatch_paths(tmp_path: Path) -> None:
    database_path = tmp_path / "phase8-existing.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-existing",
        client_order_id="paper-order-phase8-existing",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-existing",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_existing",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)
    broker = _safe_broker(order, broker_time)
    broker.existing_order = make_broker_order_snapshot(instruction)

    receipt = service.submit_approved_order(instruction, approval, broker=broker)

    assert receipt.signal_id == instruction.signal_id
    assert receipt.instruction_fingerprint == instruction.instruction_fingerprint
    assert broker.submit_calls == 0
    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_BROKER_EXISTING_ORDER_FOUND
    )

    mismatch_instruction = build_paper_order_instruction(
        signal_id="signal-phase8-existing-mismatch",
        client_order_id="paper-order-phase8-existing-mismatch",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    mismatch_approval = make_approval(
        mismatch_instruction,
        approval_id="approval-phase8-existing-mismatch",
        approved_at=broker_time - timedelta(minutes=5),
    )
    mismatch_broker = _safe_broker(order, broker_time)
    mismatch_broker.existing_order = make_broker_order_snapshot(mismatch_instruction)
    object.__setattr__(mismatch_broker.existing_order, "submitted_quantity", order.quantity + 1)

    with pytest.raises(PaperExecutionSubmissionUnknownError):
        service.submit_approved_order(
            mismatch_instruction,
            mismatch_approval,
            broker=mismatch_broker,
        )

    mismatch_attempt = repository.get_attempt(mismatch_instruction.client_order_id)
    assert mismatch_broker.submit_calls == 0
    assert mismatch_attempt.attempt_status == PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    assert mismatch_attempt.broker_order_id is None


def test_phase8_repository_rejects_forged_receipt_from_bypassed_service(tmp_path: Path) -> None:
    database_path = tmp_path / "phase8-forged-receipt.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-forged",
        client_order_id="paper-order-phase8-forged",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-forged",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.reserve_attempt(
        instruction,
        approval,
        execution_risk_approved=True,
        now_utc=broker_time,
    )
    forged_receipt = make_receipt(instruction)
    object.__setattr__(forged_receipt, "signal_id", "other-signal")

    with pytest.raises(PaperExecutionIntegrityError):
        repository.record_receipt(
            forged_receipt,
            status=PAPER_ATTEMPT_ACCEPTED,
            account_id_fingerprint="a" * 64,
            now_utc=broker_time,
            event_type="broker_order_accepted",
        )

    assert repository.get_attempt(instruction.client_order_id).broker_order_id is None


def test_phase8_terminal_states_cannot_regress_through_repository(tmp_path: Path) -> None:
    database_path = tmp_path / "phase8-terminal-lineage.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-terminal",
        client_order_id="paper-order-phase8-terminal",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-terminal",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.reserve_attempt(
        instruction,
        approval,
        execution_risk_approved=True,
        now_utc=broker_time,
    )
    repository.record_receipt(
        make_receipt(instruction),
        status=PAPER_ATTEMPT_ACCEPTED,
        account_id_fingerprint="a" * 64,
        now_utc=broker_time,
        event_type="broker_order_accepted",
    )
    before_attempt = repository.get_attempt(instruction.client_order_id)
    before_events = repository.list_events(client_order_id=instruction.client_order_id)

    with pytest.raises(PaperExecutionIntegrityError):
        repository.mark_submission_unknown(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            failure_code="late_unknown",
            now_utc=broker_time,
        )
    with pytest.raises(PaperExecutionIntegrityError):
        repository.mark_failure(
            client_order_id=instruction.client_order_id,
            signal_id=instruction.signal_id,
            status=PAPER_ATTEMPT_BLOCKED,
            failure_code="late_block",
            now_utc=broker_time,
        )

    assert repository.get_attempt(instruction.client_order_id) == before_attempt
    assert repository.list_events(client_order_id=instruction.client_order_id) == before_events


def test_phase8_wrong_signal_id_and_live_receipt_are_rejected_transactionally(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8-wrong-lineage-live.sqlite3"
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id="signal-phase8-live-receipt",
        client_order_id="paper-order-phase8-live-receipt",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + timedelta(hours=1),
    )
    approval = make_approval(
        instruction,
        approval_id="approval-phase8-live-receipt",
        approved_at=broker_time - timedelta(minutes=5),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.reserve_attempt(
        instruction,
        approval,
        execution_risk_approved=True,
        now_utc=broker_time,
    )
    before_attempt = repository.get_attempt(instruction.client_order_id)
    before_events = repository.list_events(client_order_id=instruction.client_order_id)

    with pytest.raises(PaperExecutionIntegrityError):
        repository.mark_submission_unknown(
            client_order_id=instruction.client_order_id,
            signal_id="other-signal",
            failure_code="timeout",
            now_utc=broker_time,
        )
    with pytest.raises(PaperExecutionIntegrityError):
        repository.mark_failure(
            client_order_id=instruction.client_order_id,
            signal_id="other-signal",
            status=PAPER_ATTEMPT_BLOCKED,
            failure_code="blocked",
            now_utc=broker_time,
        )
    forged = make_receipt(instruction)
    object.__setattr__(forged, "execution_environment", "alpaca_live")
    with pytest.raises(PaperExecutionIntegrityError):
        repository.record_receipt(
            forged,
            status=PAPER_ATTEMPT_ACCEPTED,
            account_id_fingerprint="a" * 64,
            now_utc=broker_time,
            event_type="broker_order_accepted",
        )

    assert repository.get_attempt(instruction.client_order_id) == before_attempt
    assert repository.list_events(client_order_id=instruction.client_order_id) == before_events
    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_RESERVED
    )


def test_phase8_configuration_kill_switch_blocks_before_broker_calls(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8-config-kill.sqlite3"
    order, broker_time, instruction, approval = _phase8_order_fixture(
        database_path,
        suffix="config-kill",
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_config_kill",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    service = PaperExecutionService(
        settings=Settings(
            enable_paper_execution=True,
            dry_run=False,
            paper_execution_kill_switch=True,
            alpaca_api_key=SecretStr("AKPHASE8TEST"),
            alpaca_secret_key=SecretStr("SKPHASE8TEST"),
        ),
        repository=repository,
    )
    broker = _safe_broker(order, broker_time)

    with pytest.raises(PaperExecutionKillSwitchError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)

    assert exc_info.value.code == "configuration_kill_switch_engaged"
    assert broker.operation_log == []
    assert broker.submit_calls == 0


def test_phase8_closed_market_refresh_race_blocks_reserved_attempt(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8-closed-refresh.sqlite3"
    order, broker_time, instruction, approval = _phase8_order_fixture(
        database_path,
        suffix="closed-refresh",
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_closed_refresh",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    broker = _safe_broker(order, broker_time)
    broker.clock_sequence = (
        BrokerClockSnapshot(
            timestamp=broker_time,
            is_open=True,
            next_open=broker_time + timedelta(days=1),
            next_close=broker_time + timedelta(hours=5),
        ),
        BrokerClockSnapshot(
            timestamp=broker_time + timedelta(minutes=1),
            is_open=False,
            next_open=broker_time + timedelta(days=1),
            next_close=broker_time + timedelta(hours=5),
        ),
    )
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)

    with pytest.raises(PaperExecutionStaleSignalError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)

    attempt = repository.get_attempt(instruction.client_order_id)
    assert exc_info.value.code == "market_closed_before_submission"
    assert broker.submit_calls == 0
    assert attempt.attempt_status == PAPER_ATTEMPT_BLOCKED
    assert attempt.failure_code == "market_closed_before_submission"
    with pytest.raises(PaperExecutionDuplicateError):
        repository.reserve_attempt(
            instruction,
            approval,
            execution_risk_approved=True,
            now_utc=broker_time,
        )


def test_phase8_exact_expiration_at_refresh_blocks_submission(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase8-exact-expiration.sqlite3"
    order, broker_time, instruction, approval = _phase8_order_fixture(
        database_path,
        suffix="exact-expiration",
        expires_after=timedelta(minutes=1),
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_exact_expiration",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    broker = _safe_broker(order, broker_time)
    broker.clock_sequence = (
        BrokerClockSnapshot(
            timestamp=broker_time,
            is_open=True,
            next_open=broker_time + timedelta(days=1),
            next_close=broker_time + timedelta(hours=5),
        ),
        BrokerClockSnapshot(
            timestamp=instruction.expires_at_utc,
            is_open=True,
            next_open=broker_time + timedelta(days=1),
            next_close=broker_time + timedelta(hours=5),
        ),
    )
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)

    with pytest.raises(PaperExecutionStaleSignalError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)

    attempt = repository.get_attempt(instruction.client_order_id)
    assert exc_info.value.code == "instruction_expired_before_submission"
    assert broker.submit_calls == 0
    assert attempt.attempt_status == PAPER_ATTEMPT_BLOCKED


def test_phase8_accepted_order_plus_ledger_failure_requires_lookup_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "phase8-ledger-failure.sqlite3"
    order, broker_time, instruction, approval = _phase8_order_fixture(
        database_path,
        suffix="ledger-failure",
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_ledger_failure",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    broker = _safe_broker(order, broker_time)
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)
    real_record_receipt = repository.record_receipt
    fail_once = True

    def failing_record_receipt(
        receipt: PaperOrderReceipt,
        *,
        status: str,
        account_id_fingerprint: str | None,
        now_utc: datetime,
        event_type: str,
    ) -> object:
        nonlocal fail_once
        if fail_once and status == PAPER_ATTEMPT_ACCEPTED:
            fail_once = False
            raise PaperExecutionIntegrityError("attempt_update_failed", "raw sqlite secret")
        return real_record_receipt(
            receipt,
            status=status,
            account_id_fingerprint=account_id_fingerprint,
            now_utc=now_utc,
            event_type=event_type,
        )

    monkeypatch.setattr(repository, "record_receipt", failing_record_receipt)

    with pytest.raises(PaperExecutionSubmissionUnknownError) as exc_info:
        service.submit_approved_order(instruction, approval, broker=broker)

    assert exc_info.value.code == "accepted_receipt_persistence_failed"
    assert broker.submit_calls == 1
    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_SUBMISSION_UNKNOWN
    )

    with pytest.raises(PaperExecutionDuplicateError):
        service.submit_approved_order(
            instruction,
            approval,
            broker=_safe_broker(order, broker_time),
        )
    reconcile_broker = _safe_broker(order, broker_time)
    reconcile_broker.existing_order = make_broker_order_snapshot(instruction)
    reconciled = service.reconcile_by_client_order_id(
        instruction.client_order_id,
        broker=reconcile_broker,
        now_utc=broker_time + timedelta(minutes=1),
    )

    assert reconciled is not None
    assert reconcile_broker.lookup_calls == 1
    assert reconcile_broker.submit_calls == 0
    assert repository.get_attempt(instruction.client_order_id).attempt_status == (
        PAPER_ATTEMPT_RECONCILED
    )


def test_phase8_successful_path_uses_fresh_clock_final_kill_switch_submit_ordering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "phase8-success-ordering.sqlite3"
    order, broker_time, instruction, approval = _phase8_order_fixture(
        database_path,
        suffix="success-ordering",
    )
    repository = SQLitePaperExecutionRepository(database_path)
    repository.set_paper_execution_kill_switch(
        engaged=False,
        reason="explicit_phase8_success_ordering",
        updated_at_utc=broker_time,
        confirmation=DISENGAGE_KILL_SWITCH_CONFIRMATION,
    )
    broker = _safe_broker(order, broker_time)
    broker.clock_sequence = (
        BrokerClockSnapshot(
            timestamp=broker_time,
            is_open=True,
            next_open=broker_time + timedelta(days=1),
            next_close=broker_time + timedelta(hours=5),
        ),
        BrokerClockSnapshot(
            timestamp=broker_time + timedelta(minutes=1),
            is_open=True,
            next_open=broker_time + timedelta(days=1),
            next_close=broker_time + timedelta(hours=5),
        ),
    )
    operations: list[str] = []
    broker.operation_log = operations
    real_kill_switch_state = repository.get_kill_switch_state

    def logged_kill_switch_state() -> object:
        operations.append("kill_switch_read")
        return real_kill_switch_state()

    monkeypatch.setattr(repository, "get_kill_switch_state", logged_kill_switch_state)
    service = PaperExecutionService(settings=_enabled_settings(), repository=repository)

    service.submit_approved_order(instruction, approval, broker=broker)

    assert broker.submit_calls == 1
    assert broker.clock_calls == 2
    assert operations[-4:] == [
        "get_order_by_client_order_id",
        "get_clock",
        "kill_switch_read",
        "submit_market_day_order",
    ]


def _approved_buy_order_and_risk(
    proposed_orders: Any,
    risk_decisions: Any,
    cost_assumptions: BacktestCostAssumptions,
) -> tuple[ProposedOrder, RiskDecision]:
    for order_row in proposed_orders.itertuples(index=False):
        risk_row = risk_decisions[
            risk_decisions["order_sequence_number"] == order_row.sequence_number
        ].iloc[0]
        if order_row.side == BUY_SIDE and bool(risk_row.approved):
            reference_open = _decimal(order_row.reference_open)
            estimate = estimate_order_cost(
                side=str(order_row.side),
                quantity=int(order_row.quantity),
                reference_open=reference_open,
                cost_assumptions=cost_assumptions,
            )
            order = ProposedOrder(
                sequence_number=int(order_row.sequence_number),
                symbol=str(order_row.symbol),
                side=str(order_row.side),
                quantity=int(order_row.quantity),
                signal_session=order_row.signal_session,
                execution_session=order_row.execution_session,
                target_position=int(order_row.target_position),
                reference_open=reference_open,
                estimated_execution_price=estimate.execution_price,
                estimated_commission=estimate.commission,
                estimated_cash_change=estimate.cash_change,
                current_cash=_decimal(order_row.current_cash),
                current_shares=int(order_row.current_shares),
            )
            portfolio = PortfolioState(
                session=order.execution_session,
                cash=order.current_cash,
                shares=order.current_shares,
                reference_price=order.reference_open,
                market_value=Decimal(order.current_shares) * order.reference_open,
                equity=order.current_cash + Decimal(order.current_shares) * order.reference_open,
            )
            risk = evaluate_order_risk(
                order,
                portfolio,
                risk_config=RiskConfig(),
                cost_assumptions=cost_assumptions,
            )
            assert risk.approved is True
            return order, risk
    raise AssertionError("deterministic Phase 7 fixture did not produce an approved buy order")


def _phase8_order_fixture(
    database_path: Path,
    *,
    suffix: str,
    expires_after: timedelta = timedelta(hours=1),
) -> tuple[ProposedOrder, datetime, PaperOrderInstruction, PaperOrderApproval]:
    artifacts = persist_phase7_artifacts(database_path)
    order, risk = _approved_buy_order_and_risk(
        artifacts.backtest.proposed_orders,
        artifacts.backtest.risk_decisions,
        artifacts.backtest.cost_assumptions,
    )
    broker_time = _broker_time(order.execution_session)
    instruction = build_paper_order_instruction(
        signal_id=f"signal-phase8-{suffix}",
        client_order_id=f"paper-order-phase8-{suffix}",
        proposed_order=order,
        original_risk_decision=risk,
        cost_assumptions=artifacts.backtest.cost_assumptions,
        created_at_utc=broker_time - timedelta(minutes=10),
        expires_at_utc=broker_time + expires_after,
    )
    approval = make_approval(
        instruction,
        approval_id=f"approval-phase8-{suffix}",
        approved_at=broker_time - timedelta(minutes=5),
    )
    return order, broker_time, instruction, approval


def _safe_broker(order: ProposedOrder, broker_time: datetime) -> FakePaperBroker:
    return FakePaperBroker(
        account=BrokerAccountSnapshot(
            status="active",
            currency="USD",
            cash=order.current_cash,
            equity=order.current_cash,
            buying_power=order.current_cash,
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
            account_id_fingerprint="a" * 64,
            retrieved_at_utc=broker_time,
        ),
        clock=BrokerClockSnapshot(
            timestamp=broker_time,
            is_open=True,
            next_open=broker_time + timedelta(days=1),
            next_close=broker_time + timedelta(hours=5),
        ),
    )


def _broker_time(session: Any) -> datetime:
    return datetime.combine(session, time(10, 30), tzinfo=NEW_YORK).astimezone(UTC)


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _enabled_settings() -> Settings:
    return Settings(
        enable_paper_execution=True,
        dry_run=False,
        paper_execution_kill_switch=False,
        alpaca_api_key=SecretStr("AKPHASE8TEST"),
        alpaca_secret_key=SecretStr("SKPHASE8TEST"),
    )


def _assert_credentials_not_persisted(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        dump = "\n".join(connection.iterdump())
    finally:
        connection.close()
    assert "AKPHASE8TEST" not in dump
    assert "SKPHASE8TEST" not in dump
