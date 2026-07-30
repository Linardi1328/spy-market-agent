from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from spy_market_agent.dashboard.client import DashboardApiClient, DashboardApiError

DASHBOARD_WARNING = (
    "Educational and experimental research dashboard. Not investment advice. Historical "
    "classification metrics and backtests do not prove profitability."
)


class DashboardClient(Protocol):
    def health(self) -> dict[str, Any]: ...

    def data_status(self) -> dict[str, Any]: ...

    def model_runs(self) -> dict[str, Any]: ...

    def model_run_detail(self, run_id: str) -> dict[str, Any]: ...

    def model_predictions(
        self,
        run_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]: ...

    def backtests(self) -> dict[str, Any]: ...

    def backtest_detail(self, run_id: str) -> dict[str, Any]: ...

    def equity(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]: ...

    def orders(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]: ...

    def risk_decisions(
        self,
        run_id: str,
        *,
        limit: int = 250,
        offset: int = 0,
    ) -> dict[str, Any]: ...

    def fills(self, run_id: str, *, limit: int = 250, offset: int = 0) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class DashboardState:
    api_available: bool
    health: dict[str, Any]
    data_status: dict[str, Any]
    model_runs: list[dict[str, Any]]
    selected_model_run: dict[str, Any] | None
    model_predictions: list[dict[str, Any]]
    backtests: list[dict[str, Any]]
    selected_backtest: dict[str, Any] | None
    equity_rows: list[dict[str, Any]]
    order_rows: list[dict[str, Any]]
    risk_decision_rows: list[dict[str, Any]]
    fill_rows: list[dict[str, Any]]
    error_message: str | None = None


def load_dashboard_state(client: DashboardClient) -> DashboardState:
    try:
        health = client.health()
        data_status = client.data_status()
        model_runs_payload = client.model_runs()
        backtests_payload = client.backtests()
        model_runs = _items(model_runs_payload)
        backtests = _items(backtests_payload)
        selected_model = None
        predictions: list[dict[str, Any]] = []
        if model_runs:
            run_id = str(model_runs[0]["run_id"])
            selected_model = client.model_run_detail(run_id)
            predictions = _items(client.model_predictions(run_id, limit=100))
        selected_backtest = None
        equity_rows: list[dict[str, Any]] = []
        order_rows: list[dict[str, Any]] = []
        risk_rows: list[dict[str, Any]] = []
        fill_rows: list[dict[str, Any]] = []
        if backtests:
            run_id = str(backtests[0]["run_id"])
            selected_backtest = client.backtest_detail(run_id)
            equity_rows = _items(client.equity(run_id, limit=250))
            order_rows = _items(client.orders(run_id, limit=250))
            risk_rows = _items(client.risk_decisions(run_id, limit=250))
            fill_rows = _items(client.fills(run_id, limit=250))
        return DashboardState(
            api_available=True,
            health=health,
            data_status=data_status,
            model_runs=model_runs,
            selected_model_run=selected_model,
            model_predictions=predictions,
            backtests=backtests,
            selected_backtest=selected_backtest,
            equity_rows=equity_rows,
            order_rows=order_rows,
            risk_decision_rows=risk_rows,
            fill_rows=fill_rows,
        )
    except (DashboardApiError, KeyError, TypeError, ValueError) as exc:
        return DashboardState(
            api_available=False,
            health={},
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
            error_message=str(exc) or "Read API is unavailable.",
        )


def render_dashboard(st: Any, state: DashboardState) -> None:
    st.set_page_config(page_title="SPY Market Agent", layout="wide")
    st.title("SPY Market Agent")
    st.warning(DASHBOARD_WARNING)
    if not state.api_available:
        st.error(state.error_message or "Read API is unavailable.")
        return

    tabs = st.tabs(
        ["Overview", "Data Quality", "Model Evaluation", "Backtest Results", "Risk and Audit"]
    )
    with tabs[0]:
        _render_overview(st, state)
    with tabs[1]:
        _render_data_quality(st, state)
    with tabs[2]:
        _render_model_evaluation(st, state)
    with tabs[3]:
        _render_backtest_results(st, state)
    with tabs[4]:
        _render_risk_audit(st, state)


def _render_overview(st: Any, state: DashboardState) -> None:
    st.subheader("Overview")
    st.write("API status:", state.health.get("status", "unknown"))
    st.write("Data available:", state.data_status.get("available", False))
    st.write(
        "Latest model run:",
        state.model_runs[0]["run_id"] if state.model_runs else "No persisted model runs",
    )
    st.write(
        "Latest backtest run:",
        state.backtests[0]["run_id"] if state.backtests else "No persisted backtests",
    )


def _render_data_quality(st: Any, state: DashboardState) -> None:
    st.subheader("Data Quality")
    if not state.data_status.get("available", False):
        st.info("No persisted market-data status is available.")
        return
    fields = [
        "symbol",
        "provider_name",
        "source_description",
        "adjustment_policy",
        "first_session",
        "last_session",
        "row_count",
        "dataset_checksum",
        "schema_version",
        "downloaded_at",
    ]
    st.dataframe(pd.DataFrame([state.data_status]).loc[:, fields])


def _render_model_evaluation(st: Any, state: DashboardState) -> None:
    st.subheader("Model Evaluation")
    model = state.selected_model_run
    if model is None:
        st.info("No persisted model evaluation is available.")
        return
    st.write("Selected model:", model["selected_model_name"])
    st.write("Selection rationale:", model["selection_reason"])
    st.write("Classification metrics do not establish profitability.")
    st.dataframe(pd.DataFrame(model["validation_metric_snapshots"]))
    st.dataframe(pd.DataFrame([model["final_test_metrics"]]))
    if state.model_predictions:
        prediction_frame = pd.DataFrame(state.model_predictions)
        st.line_chart(prediction_frame.set_index("session")["probability_positive"])
        st.dataframe(prediction_frame)


def _render_backtest_results(st: Any, state: DashboardState) -> None:
    st.subheader("Backtest Results")
    backtest = state.selected_backtest
    if backtest is None:
        st.info("No persisted backtest is available.")
        return
    metrics = backtest["metrics"]
    st.metric("Initial Equity", metrics["initial_cash"])
    st.metric("Final Equity", metrics["final_equity"])
    st.metric("Total Return", metrics["total_return"])
    st.metric("Maximum Drawdown", metrics["maximum_drawdown"])
    st.metric("Turnover", metrics["turnover_ratio"])
    st.metric("Exposure", metrics["exposure_fraction"])
    st.metric("Costs", metrics["total_transaction_cost"])
    st.write("Historical backtests are approximations and do not guarantee future results.")
    if state.equity_rows:
        equity_frame = pd.DataFrame(state.equity_rows)
        st.line_chart(equity_frame.set_index("session")["equity"])
        st.line_chart(equity_frame.set_index("session")["drawdown"])
        st.dataframe(equity_frame)


def _render_risk_audit(st: Any, state: DashboardState) -> None:
    st.subheader("Risk and Audit")
    backtest = state.selected_backtest
    if backtest is None:
        st.info("No persisted risk audit is available.")
        return
    st.dataframe(pd.DataFrame([backtest["risk_config"]]))
    st.write("SPY-only, long-only, no leverage, no fractional shares.")
    if state.risk_decision_rows:
        risk_frame = pd.DataFrame(state.risk_decision_rows)
        st.write("Approved decisions:", int(risk_frame["approved"].sum()))
        st.write("Rejected decisions:", int((~risk_frame["approved"]).sum()))
        st.dataframe(risk_frame)
    if state.order_rows:
        st.dataframe(pd.DataFrame(state.order_rows))
    if state.fill_rows:
        st.dataframe(pd.DataFrame(state.fill_rows))


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items", [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("API payload items must be a list of objects.")
    return [dict(item) for item in items]


def create_default_client(
    *,
    base_url: str = "http://127.0.0.1:8000",
    timeout_seconds: float = 5.0,
) -> DashboardApiClient:
    return DashboardApiClient(base_url=base_url, timeout_seconds=timeout_seconds)


__all__ = [
    "DASHBOARD_WARNING",
    "DashboardClient",
    "DashboardState",
    "create_default_client",
    "load_dashboard_state",
    "render_dashboard",
]
