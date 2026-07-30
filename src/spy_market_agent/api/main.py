from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from spy_market_agent.api.schemas import (
    ApiErrorResponse,
    BacktestDetailResponse,
    BacktestRunListResponse,
    DataStatusResponse,
    EquityPageResponse,
    FillPageResponse,
    HealthResponse,
    ModelRunDetailResponse,
    ModelRunListResponse,
    OrderPageResponse,
    PredictionPageResponse,
    RiskDecisionPageResponse,
)
from spy_market_agent.api.services import MAX_PAGE_LIMIT, ReadRepository, ReadService
from spy_market_agent.persistence.models import (
    PersistenceError,
    PersistenceNotFoundError,
)
from spy_market_agent.persistence.repositories import SQLiteArtifactRepository

DEFAULT_SQLITE_DATABASE_PATH = "./spy_market_agent.sqlite3"
LimitParam = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)]
OffsetParam = Annotated[int, Query(ge=0)]


def create_app(
    *,
    repository: ReadRepository | None = None,
    service: ReadService | None = None,
    database_path: str | None = None,
) -> FastAPI:
    read_service = service
    if read_service is None:
        read_repository = repository or SQLiteArtifactRepository(
            database_path or DEFAULT_SQLITE_DATABASE_PATH
        )
        read_service = ReadService(read_repository)

    app = FastAPI(title="SPY Market Agent Read API", version="1.0.0")

    @app.exception_handler(PersistenceNotFoundError)
    async def _not_found_handler(
        _request: Request,
        exc: PersistenceNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ApiErrorResponse(code=exc.code, message=str(exc)).model_dump(),
        )

    @app.exception_handler(PersistenceError)
    async def _persistence_handler(_request: Request, exc: PersistenceError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=ApiErrorResponse(
                code=exc.code,
                message="Persisted research data is unavailable or invalid.",
            ).model_dump(),
        )

    @app.exception_handler(ValueError)
    async def _value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ApiErrorResponse(code="invalid_request", message=str(exc)).model_dump(),
        )

    def service_dependency() -> ReadService:
        return read_service

    service_dependency_marker = Depends(service_dependency)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/api/v1/data/status", response_model=DataStatusResponse)
    def data_status(reads: ReadService = service_dependency_marker) -> DataStatusResponse:
        return reads.data_status()

    @app.get("/api/v1/model-runs", response_model=ModelRunListResponse)
    def model_runs(reads: ReadService = service_dependency_marker) -> ModelRunListResponse:
        return reads.model_runs()

    @app.get("/api/v1/model-runs/{run_id}", response_model=ModelRunDetailResponse)
    def model_run_detail(
        run_id: str,
        reads: ReadService = service_dependency_marker,
    ) -> ModelRunDetailResponse:
        return reads.model_run_detail(run_id)

    @app.get("/api/v1/model-runs/{run_id}/predictions", response_model=PredictionPageResponse)
    def model_predictions(
        run_id: str,
        reads: ReadService = service_dependency_marker,
        limit: LimitParam = 100,
        offset: OffsetParam = 0,
    ) -> PredictionPageResponse:
        return reads.model_predictions(run_id, limit=limit, offset=offset)

    @app.get("/api/v1/backtests", response_model=BacktestRunListResponse)
    def backtests(reads: ReadService = service_dependency_marker) -> BacktestRunListResponse:
        return reads.backtests()

    @app.get("/api/v1/backtests/{run_id}", response_model=BacktestDetailResponse)
    def backtest_detail(
        run_id: str,
        reads: ReadService = service_dependency_marker,
    ) -> BacktestDetailResponse:
        return reads.backtest_detail(run_id)

    @app.get("/api/v1/backtests/{run_id}/equity", response_model=EquityPageResponse)
    def backtest_equity(
        run_id: str,
        reads: ReadService = service_dependency_marker,
        limit: LimitParam = 100,
        offset: OffsetParam = 0,
    ) -> EquityPageResponse:
        return reads.equity(run_id, limit=limit, offset=offset)

    @app.get("/api/v1/backtests/{run_id}/orders", response_model=OrderPageResponse)
    def backtest_orders(
        run_id: str,
        reads: ReadService = service_dependency_marker,
        limit: LimitParam = 100,
        offset: OffsetParam = 0,
    ) -> OrderPageResponse:
        return reads.orders(run_id, limit=limit, offset=offset)

    @app.get(
        "/api/v1/backtests/{run_id}/risk-decisions",
        response_model=RiskDecisionPageResponse,
    )
    def backtest_risk_decisions(
        run_id: str,
        reads: ReadService = service_dependency_marker,
        limit: LimitParam = 100,
        offset: OffsetParam = 0,
    ) -> RiskDecisionPageResponse:
        return reads.risk_decisions(run_id, limit=limit, offset=offset)

    @app.get("/api/v1/backtests/{run_id}/fills", response_model=FillPageResponse)
    def backtest_fills(
        run_id: str,
        reads: ReadService = service_dependency_marker,
        limit: LimitParam = 100,
        offset: OffsetParam = 0,
    ) -> FillPageResponse:
        return reads.fills(run_id, limit=limit, offset=offset)

    _assert_read_only_routes(app.routes)
    return app


def _assert_read_only_routes(routes: Sequence[object]) -> None:
    state_changing = {"POST", "PUT", "PATCH", "DELETE"}
    for route in routes:
        methods = getattr(route, "methods", None)
        if methods is not None and state_changing.intersection(set(methods)):
            raise RuntimeError("Phase 7 API may only expose read-only application routes.")


__all__ = ["DEFAULT_SQLITE_DATABASE_PATH", "create_app"]
