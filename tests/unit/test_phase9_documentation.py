from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from fastapi.routing import APIRoute

from spy_market_agent.api import create_app

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_DOCUMENTS = (
    "docs/ARCHITECTURE.md",
    "docs/REPRODUCIBILITY.md",
    "docs/WORKFLOWS.md",
    "docs/SECURITY_AND_SAFETY.md",
    "docs/DEMO_GUIDE.md",
    "docs/PORTFOLIO_OVERVIEW.md",
    "docs/V2_PHASE_02_REAL_HISTORICAL_BENCHMARK_SPEC.md",
    "CHANGELOG.md",
    "RELEASE_NOTES_V1.0.0.md",
    "RELEASE_NOTES_V2.0.0_ALPHA_1.md",
    "VERSION_1_RELEASE_CHECKLIST.md",
    "VERSION_2_PHASE_01_RELEASE_CHECKLIST.md",
    "reviews/PHASE_09_REVIEW.md",
    "reviews/VERSION_1_FINAL_REVIEW.md",
    "reviews/V2_PHASE_01_REVIEW.md",
)

DOCUMENTED_MODULE_PATHS = (
    "src/spy_market_agent/config",
    "src/spy_market_agent/market_data",
    "src/spy_market_agent/validation",
    "src/spy_market_agent/features",
    "src/spy_market_agent/datasets",
    "src/spy_market_agent/modeling",
    "src/spy_market_agent/strategies",
    "src/spy_market_agent/risk",
    "src/spy_market_agent/backtesting",
    "src/spy_market_agent/persistence",
    "src/spy_market_agent/api",
    "src/spy_market_agent/dashboard",
    "src/spy_market_agent/execution",
    "src/spy_market_agent/execution/alpaca_paper.py",
)

EXPECTED_GET_ROUTES = {
    "/health",
    "/api/v1/data/status",
    "/api/v1/model-runs",
    "/api/v1/model-runs/{run_id}",
    "/api/v1/model-runs/{run_id}/predictions",
    "/api/v1/backtests",
    "/api/v1/backtests/{run_id}",
    "/api/v1/backtests/{run_id}/equity",
    "/api/v1/backtests/{run_id}/orders",
    "/api/v1/backtests/{run_id}/risk-decisions",
    "/api/v1/backtests/{run_id}/fills",
    "/api/v1/paper-trading/status",
    "/api/v1/paper-orders",
    "/api/v1/paper-orders/{client_order_id}",
}


def _application_get_routes() -> set[str]:
    app = create_app()
    route_inventory: set[str] = set()
    excluded_routes = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = route.methods or set()
        if "GET" in methods and route.path not in excluded_routes:
            route_inventory.add(route.path)

    return route_inventory


def _repo_document_texts() -> dict[str, str]:
    paths = ("README.md", *REQUIRED_DOCUMENTS)
    return {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}


def _fenced_blocks(text: str) -> Iterator[tuple[str, str]]:
    pattern = re.compile(r"```(?P<language>[^\n]*)\n(?P<body>.*?)```", re.DOTALL)
    for match in pattern.finditer(text):
        yield match.group("language").strip().lower(), match.group("body")


def test_phase9_documentation_files_exist() -> None:
    for path in REQUIRED_DOCUMENTS:
        assert (ROOT / path).is_file(), path


def test_readme_internal_links_resolve_to_repository_files() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", readme)

    assert links
    for link in links:
        if "://" in link or link.startswith("#"):
            continue
        target = ROOT / link.split("#", 1)[0]
        assert target.exists(), link


def test_documented_module_paths_exist() -> None:
    architecture = (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")

    for path in DOCUMENTED_MODULE_PATHS:
        assert path in architecture
        assert (ROOT / path).exists(), path


def test_documented_fastapi_routes_match_application_inventory() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert _application_get_routes() == EXPECTED_GET_ROUTES
    for route in sorted(EXPECTED_GET_ROUTES):
        assert f"GET {route}" in readme


def test_api_route_versions_remain_v1() -> None:
    routes = _application_get_routes()

    assert "/health" in routes
    assert all(route == "/health" or route.startswith("/api/v1/") for route in routes)
    assert not any(route.startswith("/api/v2/") for route in routes)


def test_documented_code_examples_do_not_submit_paper_orders() -> None:
    forbidden_executable_terms = (
        "submit_approved_order",
        "submit_market_day_order",
        "AlpacaPaperBroker",
        "TradingClient",
    )
    executable_languages = {"bash", "sh", "shell", "python", "py"}

    for path, text in _repo_document_texts().items():
        for language, body in _fenced_blocks(text):
            if language not in executable_languages:
                continue
            assert "paper=False" not in body, path
            assert "https://api.alpaca.markets" not in body, path
            for term in forbidden_executable_terms:
                assert term not in body, f"{path}: {term}"


def test_version_1_safety_statements_remain_documented() -> None:
    docs = _repo_document_texts()
    combined = "\n".join(docs.values()).lower()

    assert "not investment advice" in combined
    assert "no live trading" in combined
    assert "no market-data downloader" in combined
    assert "no automatic paper-order submission" in combined
    assert "dual kill switches" in combined
    assert "lookup-only reconciliation" in combined
    assert "at most one spy paper-execution attempt" in combined


def test_version_2_alpha_release_documents_are_consistent() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "FUTURE_ROADMAP.md").read_text(encoding="utf-8")
    spec = (ROOT / "docs/V2_PHASE_01_REAL_SPY_DATA_SPEC.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "RELEASE_NOTES_V2.0.0_ALPHA_1.md").read_text(encoding="utf-8")
    checklist = (ROOT / "VERSION_2_PHASE_01_RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    review = (ROOT / "reviews/V2_PHASE_01_REVIEW.md").read_text(encoding="utf-8")
    combined = "\n".join((readme, changelog, roadmap, spec, release_notes, checklist, review))

    assert "Package version: `2.0.0a1`" in readme
    assert "Release identifier: `v2.0.0-alpha.1`" in readme
    assert "V2 Phase 1: accepted and complete - Real SPY Data Foundation" in readme
    assert "Version 2 Phase 2 has not begun" in readme
    assert "## [2.0.0-alpha.1] - 2026-08-05" in changelog
    assert "Corresponding Python package version: `2.0.0a1`" in changelog
    assert "Status: Accepted for v2.0.0-alpha.1 release" in spec
    assert "Accepted - Version 2 Real SPY Data Foundation" in roadmap
    assert "Specification in review; implementation not started" in roadmap
    assert "Implementation in review" not in spec
    assert "Git release identifier: `v2.0.0-alpha.1`" in release_notes
    assert "does not evaluate model accuracy" in release_notes
    assert "does not claim profitability" in release_notes
    assert "does not add live-money execution" in release_notes
    assert "No Git tag created on the review branch" in checklist
    assert "Create annotated `v2.0.0-alpha.1` tag" in checklist
    assert "Phase 1 accepted; release metadata verified" in review
    assert "preparing the tag" not in combined.lower()
    assert "release preparation in review" not in combined.lower()
    assert "Planned Git tag" not in combined
    assert "tag already exists" not in combined.lower()


def test_version_2_phase2_specification_is_planning_only() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "FUTURE_ROADMAP.md").read_text(encoding="utf-8")
    spec = (ROOT / "docs/V2_PHASE_02_REAL_HISTORICAL_BENCHMARK_SPEC.md").read_text(encoding="utf-8")
    combined = "\n".join((readme, changelog, roadmap, spec)).lower()

    assert "Package version: `2.0.0a1`" in readme
    assert "v2.0.0-alpha.2" in spec
    assert "2.0.0a2" in spec
    assert "Status: Planning" in spec
    assert "awaiting review and implementation approval" in spec
    assert "This specification does not authorize implementation" in spec
    assert "Phase 2 implementation remains unstarted" in changelog
    assert "Package/runtime version remains `2.0.0a1`" in changelog
    assert "No benchmark or profitability result has been produced" in changelog
    assert "Specification in review; implementation not started" in roadmap
    assert "Version 2 Phase 2 has not begun" in readme
    assert "no benchmark or profitability result has been produced" in combined
    assert "does not authorize new model research, live execution, shadow" in combined
    assert "phase 2 implementation must not begin" in combined
    assert "phase 2 benchmark passed" not in combined
    assert "phase 2 is implemented" not in combined
    assert "profitability is guaranteed" not in combined
    assert "live-money readiness: approved" not in combined
