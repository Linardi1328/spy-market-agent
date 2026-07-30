from __future__ import annotations

import inspect
from typing import Any

import httpx
import pytest

import spy_market_agent.dashboard as dashboard
import spy_market_agent.dashboard.app as dashboard_app
import spy_market_agent.dashboard.client as dashboard_client
from spy_market_agent.dashboard import DASHBOARD_WARNING
from spy_market_agent.dashboard.app import DashboardState, load_dashboard_state, render_dashboard
from spy_market_agent.dashboard.client import DashboardApiClient, DashboardApiError


class FakeClient:
    def __init__(self, *, populated: bool = True, fail: bool = False) -> None:
        self.populated = populated
        self.fail = fail

    def health(self) -> dict[str, Any]:
        if self.fail:
            raise DashboardApiError("api unavailable")
        return {"status": "ok"}

    def data_status(self) -> dict[str, Any]:
        return {"available": self.populated, "symbol": "SPY"}

    def model_runs(self) -> dict[str, Any]:
        return {"items": [{"run_id": "model-run-1"}] if self.populated else []}

    def model_run_detail(self, run_id: str) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "selected_model_name": "logistic_regression",
            "selection_reason": "Selected for test.",
            "validation_metric_snapshots": [],
            "final_test_metrics": {"row_count": 1},
        }

    def model_predictions(
        self,
        run_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        _ = (run_id, limit)
        return {
            "items": [
                {
                    "sequence_number": offset,
                    "session": "2025-01-02",
                    "probability_positive": 0.5,
                }
            ]
        }

    def backtests(self) -> dict[str, Any]:
        return {"items": [{"run_id": "backtest-run-1"}] if self.populated else []}

    def backtest_detail(self, run_id: str) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "metrics": {
                "initial_cash": "10000",
                "final_equity": "10050",
                "total_return": 0.005,
                "maximum_drawdown": 0.01,
                "turnover_ratio": 0.2,
                "exposure_fraction": 0.5,
                "total_transaction_cost": "1.25",
            },
            "risk_config": {
                "supported_symbol": "SPY",
                "allow_short_selling": False,
                "allow_leverage": False,
                "allow_fractional_shares": False,
                "maximum_position_weight": 1.0,
            },
        }

    def equity(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]:
        _ = (run_id, limit, offset)
        return {"items": [{"session": "2025-01-03", "equity": "10050", "drawdown": 0.0}]}

    def orders(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]:
        _ = (run_id, limit, offset)
        return {"items": [{"sequence_number": 1, "symbol": "SPY"}]}

    def risk_decisions(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]:
        _ = (run_id, limit, offset)
        return {
            "items": [{"order_sequence_number": 1, "approved": True, "reason_codes": ["approved"]}]
        }

    def fills(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]:
        _ = (run_id, limit, offset)
        return {"items": [{"order_sequence_number": 1, "risk_approved": True}]}


class FakeTab:
    def __enter__(self) -> FakeTab:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeStreamlit:
    def __init__(self) -> None:
        self.text: list[str] = []

    def __getattr__(self, name: str) -> Any:
        def recorder(*args: object, **_kwargs: object) -> object:
            self.text.extend(str(arg) for arg in args)
            if name == "tabs":
                return [FakeTab(), FakeTab(), FakeTab(), FakeTab(), FakeTab()]
            return None

        return recorder


def test_dashboard_http_client_parses_responses_and_handles_api_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(503, json={"code": "unavailable"})

    client = DashboardApiClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    )

    assert client.health() == {"status": "ok"}
    with pytest.raises(DashboardApiError, match="unavailable"):
        client.data_status()
    client.close()


def test_dashboard_state_handles_empty_populated_and_unavailable_api() -> None:
    empty = load_dashboard_state(FakeClient(populated=False))
    populated = load_dashboard_state(FakeClient(populated=True))
    unavailable = load_dashboard_state(FakeClient(fail=True))

    assert empty.api_available is True
    assert empty.selected_model_run is None
    assert populated.selected_model_run is not None
    assert populated.selected_backtest is not None
    assert unavailable.api_available is False


def test_dashboard_rendering_shows_required_warning_and_no_write_controls() -> None:
    streamlit = FakeStreamlit()
    state = DashboardState(
        api_available=True,
        health={"status": "ok"},
        data_status={"available": False},
        model_runs=[],
        selected_model_run=None,
        model_predictions=[],
        backtests=[],
        selected_backtest=None,
        equity_rows=[],
        order_rows=[],
        risk_decision_rows=[],
        fill_rows=[],
    )

    render_dashboard(streamlit, state)
    rendered_text = " ".join(streamlit.text).lower()

    assert "not investment advice" in rendered_text
    assert "submit" not in rendered_text
    assert "approve order" not in rendered_text


def test_dashboard_import_smoke_public_exports_and_no_database_access() -> None:
    source = inspect.getsource(dashboard)
    app_source = inspect.getsource(dashboard_app)
    client_source = inspect.getsource(dashboard_client)

    assert "DashboardApiClient" in dashboard.__all__
    assert "persistence" not in source + app_source + client_source
    assert "button" not in (source + app_source + client_source).lower()
    assert "broker" not in (source + app_source + client_source).lower()
    assert "not investment advice" in DASHBOARD_WARNING.lower()
