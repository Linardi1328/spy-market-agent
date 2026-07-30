from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from spy_market_agent.api import create_app
from spy_market_agent.persistence import initialize_database
from unit.phase7_helpers import BACKTEST_RUN_ID, MODEL_RUN_ID, persist_phase7_artifacts


def test_app_factory_health_does_not_initialize_database(tmp_path: Path) -> None:
    database_path = tmp_path / "not-created.sqlite3"
    client = TestClient(create_app(database_path=str(database_path)))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert not database_path.exists()


def test_empty_initialized_database_returns_safe_empty_responses(tmp_path: Path) -> None:
    database_path = tmp_path / "empty.sqlite3"
    initialize_database(database_path)
    client = TestClient(create_app(database_path=str(database_path)))

    assert client.get("/api/v1/data/status").json()["available"] is False
    assert client.get("/api/v1/model-runs").json() == {
        "items": [],
        "count": 0,
        "educational_warning": (
            "Educational and experimental research output only. Not investment advice and not "
            "proof of profitability."
        ),
    }
    assert client.get("/api/v1/backtests").json()["items"] == []


def test_read_endpoints_return_persisted_results_with_ordered_paginated_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase7.sqlite3"
    persist_phase7_artifacts(database_path)
    client = TestClient(create_app(database_path=str(database_path)))

    data_status = client.get("/api/v1/data/status").json()
    model_runs = client.get("/api/v1/model-runs").json()
    model_detail = client.get(f"/api/v1/model-runs/{MODEL_RUN_ID}").json()
    predictions = client.get(
        f"/api/v1/model-runs/{MODEL_RUN_ID}/predictions",
        params={"limit": 3, "offset": 1},
    ).json()
    backtests = client.get("/api/v1/backtests").json()
    backtest_detail = client.get(f"/api/v1/backtests/{BACKTEST_RUN_ID}").json()
    equity = client.get(
        f"/api/v1/backtests/{BACKTEST_RUN_ID}/equity",
        params={"limit": 2, "offset": 0},
    ).json()
    orders = client.get(f"/api/v1/backtests/{BACKTEST_RUN_ID}/orders").json()
    decisions = client.get(f"/api/v1/backtests/{BACKTEST_RUN_ID}/risk-decisions").json()
    fills = client.get(f"/api/v1/backtests/{BACKTEST_RUN_ID}/fills").json()

    assert data_status["available"] is True
    assert data_status["symbol"] == "SPY"
    assert model_runs["items"][0]["run_id"] == MODEL_RUN_ID
    assert "not investment advice" in model_detail["educational_warning"].lower()
    assert model_detail["limitation"] == "Classification metrics do not establish profitability."
    assert predictions["items"][0]["sequence_number"] == 1
    assert predictions["items"][0]["session"] < predictions["items"][1]["session"]
    assert backtests["items"][0]["run_id"] == BACKTEST_RUN_ID
    assert isinstance(backtest_detail["metrics"]["final_equity"], str)
    assert backtest_detail["risk_config"]["supported_symbol"] == "SPY"
    assert equity["items"][0]["session"] < equity["items"][1]["session"]
    assert orders["items"][0]["symbol"] == "SPY"
    assert decisions["items"][0]["reason_codes"]
    assert fills["items"][0]["risk_approved"] is True


def test_unknown_run_ids_and_invalid_databases_return_sanitized_structured_errors(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase7.sqlite3"
    initialize_database(database_path)
    client = TestClient(create_app(database_path=str(database_path)))

    not_found = client.get("/api/v1/model-runs/missing")
    unavailable = TestClient(create_app(database_path=str(tmp_path / "missing.sqlite3"))).get(
        "/api/v1/model-runs"
    )

    assert not_found.status_code == 404
    assert not_found.json()["code"] == "model_run_not_found"
    assert unavailable.status_code == 503
    assert "missing.sqlite3" not in unavailable.text


def test_pagination_validation_and_read_only_routes(tmp_path: Path) -> None:
    database_path = tmp_path / "phase7.sqlite3"
    initialize_database(database_path)
    app = create_app(database_path=str(database_path))
    client = TestClient(app)

    response = client.get("/api/v1/model-runs/missing/predictions", params={"limit": 999})

    assert response.status_code == 422
    state_changing = {"POST", "PUT", "PATCH", "DELETE"}
    for route in app.routes:
        methods: set[str] = set(getattr(route, "methods", set()) or set())
        assert not state_changing.intersection(methods)
