from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from spy_market_agent.market_data.calendar import XNYSCalendar


def test_calendar_identifies_valid_xnys_sessions() -> None:
    calendar = XNYSCalendar()

    assert calendar.calendar_code == "XNYS"
    assert calendar.is_session(date(2024, 1, 2))
    assert not calendar.is_session(date(2024, 1, 6))
    assert not calendar.is_session(date(2024, 1, 1))


def test_sessions_between_excludes_weekends_and_holidays() -> None:
    calendar = XNYSCalendar()

    sessions = calendar.sessions_between(date(2024, 1, 1), date(2024, 1, 8))

    assert sessions == (
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
    )


def test_missing_sessions_reports_only_expected_exchange_sessions() -> None:
    calendar = XNYSCalendar()

    missing = calendar.missing_sessions((date(2024, 1, 2), date(2024, 1, 4)))

    assert missing == (date(2024, 1, 3),)


def test_session_completion_uses_injected_aware_timestamp() -> None:
    calendar = XNYSCalendar()

    assert not calendar.is_session_complete(
        date(2024, 1, 5),
        as_of=datetime(2024, 1, 5, 15, 0, tzinfo=UTC),
    )
    assert calendar.is_session_complete(
        date(2024, 1, 5),
        as_of=datetime(2024, 1, 5, 22, 0, tzinfo=UTC),
    )


def test_calendar_converts_aware_timestamps_to_utc() -> None:
    calendar = XNYSCalendar()

    new_york_time = datetime(2024, 1, 5, 16, 0, tzinfo=ZoneInfo("America/New_York"))

    assert calendar.to_utc(new_york_time) == datetime(2024, 1, 5, 21, 0, tzinfo=UTC)


def test_calendar_rejects_naive_timestamps() -> None:
    calendar = XNYSCalendar()

    with pytest.raises(ValueError, match="timezone-aware"):
        calendar.to_utc(datetime(2024, 1, 5, 16, 0))
