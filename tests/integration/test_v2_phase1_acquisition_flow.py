from __future__ import annotations

import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from spy_market_agent.market_data.acquisition import AcquisitionRequest, MarketDataCredentials
from spy_market_agent.market_data.alpaca_provider import AlpacaMarketDataProvider
from spy_market_agent.market_data.errors import ChecksumMismatch, ExistingDatasetConflict
from spy_market_agent.market_data.pipeline import acquire_historical_spy_data
from spy_market_agent.market_data.storage import DatasetStore

FIXED_NOW = datetime(2024, 1, 8, 22, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return FIXED_NOW


def make_request(
    *, data_root: Path = Path("data"), adjustment_mode: str = "raw"
) -> AcquisitionRequest:
    return AcquisitionRequest(
        symbol="SPY",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 5),
        timeframe="1Day",
        provider="alpaca",
        feed="sip",
        adjustment_mode=adjustment_mode,
        data_root=data_root,
        acknowledge_provider_terms=True,
    )


def valid_pages(*, final_close: str = "103.50") -> list[dict[str, Any]]:
    return [
        {
            "bars": {
                "SPY": [
                    {
                        "t": "2024-01-02T05:00:00Z",
                        "o": "100.00",
                        "h": "101.00",
                        "l": "99.50",
                        "c": "100.50",
                        "v": "1000000",
                    },
                    {
                        "t": "2024-01-03T05:00:00Z",
                        "o": "100.50",
                        "h": "102.00",
                        "l": "100.00",
                        "c": "101.25",
                        "v": "1000100",
                    },
                ]
            },
            "next_page_token": "page-2",
        },
        {
            "bars": {
                "SPY": [
                    {
                        "t": "2024-01-04T05:00:00Z",
                        "o": "101.25",
                        "h": "103.00",
                        "l": "101.00",
                        "c": "102.75",
                        "v": "1000200",
                    },
                    {
                        "t": "2024-01-05T05:00:00Z",
                        "o": "102.75",
                        "h": "104.00",
                        "l": "102.50",
                        "c": final_close,
                        "v": "1000300",
                    },
                ]
            },
            "next_page_token": None,
        },
    ]


def missing_session_pages() -> list[dict[str, Any]]:
    pages = valid_pages()
    pages[0]["bars"]["SPY"] = [pages[0]["bars"]["SPY"][0]]
    return pages


class FakePageClient:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = [dict(page) for page in pages]

    def get(self, *, path: str, data: dict[str, Any]) -> dict[str, Any]:
        assert path == "/stocks/bars"
        assert data["symbols"] == "SPY"
        return self.pages.pop(0)


def make_provider(pages: list[dict[str, Any]]) -> AlpacaMarketDataProvider:
    return AlpacaMarketDataProvider(
        client_factory=lambda _credentials: FakePageClient(pages),
        sleep=lambda _seconds: None,
    )


def test_fake_provider_pages_write_raw_canonical_manifest_and_verify(tmp_path: Path) -> None:
    artifacts = acquire_historical_spy_data(
        make_request(),
        provider=make_provider(valid_pages()),
        credentials=MarketDataCredentials(api_key="key", secret_key="secret"),
        clock=fixed_clock,
        repository_root=tmp_path,
    )

    assert artifacts.manifest.row_count == 4
    assert artifacts.manifest.missing_session_summary.count == 0
    assert artifacts.manifest.source_checksum
    assert artifacts.manifest.canonical_content_checksum
    assert artifacts.manifest.generated_file_locations.raw_snapshot_path.startswith("data/raw/")
    assert artifacts.manifest.generated_file_locations.canonical_path.startswith("data/canonical/")
    assert artifacts.manifest.generated_file_locations.manifest_path.startswith("data/manifests/")

    store = DatasetStore(Path("data"), repository_root=tmp_path)
    manifest = store.verify_manifest_artifacts(
        tmp_path / artifacts.manifest.generated_file_locations.manifest_path
    )
    assert manifest.dataset_id == artifacts.manifest.dataset_id


def test_repeated_unchanged_acquisition_is_idempotent(tmp_path: Path) -> None:
    request = make_request()
    credentials = MarketDataCredentials(api_key="key", secret_key="secret")
    first = acquire_historical_spy_data(
        request,
        provider=make_provider(valid_pages()),
        credentials=credentials,
        clock=fixed_clock,
        repository_root=tmp_path,
    )
    second = acquire_historical_spy_data(
        request,
        provider=make_provider(valid_pages()),
        credentials=credentials,
        clock=fixed_clock,
        repository_root=tmp_path,
    )

    assert first.manifest.dataset_id == second.manifest.dataset_id
    assert first.manifest.canonical_content_checksum == second.manifest.canonical_content_checksum
    assert second.reused_existing is True
    assert second.created_files == ()


def test_changed_provider_content_changes_dataset_identity(tmp_path: Path) -> None:
    request = make_request()
    credentials = MarketDataCredentials(api_key="key", secret_key="secret")
    first = acquire_historical_spy_data(
        request,
        provider=make_provider(valid_pages()),
        credentials=credentials,
        clock=fixed_clock,
        repository_root=tmp_path,
    )
    second = acquire_historical_spy_data(
        request,
        provider=make_provider(valid_pages(final_close="103.75")),
        credentials=credentials,
        clock=fixed_clock,
        repository_root=tmp_path,
    )

    assert first.manifest.canonical_content_checksum != second.manifest.canonical_content_checksum
    assert first.manifest.dataset_id != second.manifest.dataset_id


def test_corrupted_artifact_fails_closed_on_repeat_and_verify(tmp_path: Path) -> None:
    request = make_request()
    credentials = MarketDataCredentials(api_key="key", secret_key="secret")
    artifacts = acquire_historical_spy_data(
        request,
        provider=make_provider(valid_pages()),
        credentials=credentials,
        clock=fixed_clock,
        repository_root=tmp_path,
    )
    canonical_path = tmp_path / artifacts.manifest.generated_file_locations.canonical_path
    canonical_path.write_text("corrupted\n", encoding="utf-8")
    store = DatasetStore(Path("data"), repository_root=tmp_path)

    with pytest.raises(ChecksumMismatch):
        store.verify_manifest_artifacts(
            tmp_path / artifacts.manifest.generated_file_locations.manifest_path
        )
    with pytest.raises(ExistingDatasetConflict):
        acquire_historical_spy_data(
            request,
            provider=make_provider(valid_pages()),
            credentials=credentials,
            clock=fixed_clock,
            repository_root=tmp_path,
        )


def test_corrupted_manifest_fails_verification(tmp_path: Path) -> None:
    artifacts = acquire_historical_spy_data(
        make_request(),
        provider=make_provider(valid_pages()),
        credentials=MarketDataCredentials(api_key="key", secret_key="secret"),
        clock=fixed_clock,
        repository_root=tmp_path,
    )
    manifest_path = tmp_path / artifacts.manifest.generated_file_locations.manifest_path
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace("1.0.0", "9.9.9"), encoding="utf-8"
    )
    store = DatasetStore(Path("data"), repository_root=tmp_path)

    with pytest.raises(ChecksumMismatch):
        store.verify_manifest_artifacts(manifest_path)


def test_missing_xnys_session_rejects_pipeline(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="expected XNYS sessions are missing"):
        acquire_historical_spy_data(
            make_request(),
            provider=make_provider(missing_session_pages()),
            credentials=MarketDataCredentials(api_key="key", secret_key="secret"),
            clock=fixed_clock,
            repository_root=tmp_path,
        )


def test_api_and_dashboard_startup_do_not_acquire_market_data(tmp_path: Path) -> None:
    code = (
        "from spy_market_agent.api import create_app; "
        "import spy_market_agent.dashboard.streamlit_app as app; "
        "create_app(); "
        "print(hasattr(app, 'main')); "
        "import pathlib; print(list(pathlib.Path('.').iterdir()))"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == ["True", "[]"]
