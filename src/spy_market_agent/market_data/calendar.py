from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Protocol, cast

import exchange_calendars as xcals
import pandas as pd

MARKET_CALENDAR = "XNYS"
MARKET_TIMEZONE = "America/New_York"


class TradingCalendar(Protocol):
    """Internal calendar interface used by validation code."""

    name: str
    timezone_name: str

    @property
    def calendar_code(self) -> str:
        """Canonical exchange-calendar identifier."""

    def is_session(self, session: date) -> bool:
        """Return whether the date is a valid exchange session."""

    def sessions_between(self, start_session: date, end_session: date) -> tuple[date, ...]:
        """Return valid exchange sessions between two dates, inclusive."""

    def missing_sessions(self, observed_sessions: tuple[date, ...]) -> tuple[date, ...]:
        """Return expected sessions absent from an observed ordered session sequence."""

    def is_session_complete(self, session: date, *, as_of: datetime) -> bool:
        """Return whether the daily session is complete at the injected timestamp."""

    def to_utc(self, timestamp: datetime) -> datetime:
        """Convert a timezone-aware timestamp to UTC."""


class XNYSCalendar:
    """Small adapter around `exchange-calendars` for NYSE daily sessions."""

    name = MARKET_CALENDAR
    timezone_name = MARKET_TIMEZONE

    def __init__(self) -> None:
        self._calendar = xcals.get_calendar(MARKET_CALENDAR)

    @property
    def calendar_code(self) -> str:
        return MARKET_CALENDAR

    def is_session(self, session: date) -> bool:
        return bool(self._calendar.is_session(pd.Timestamp(session)))

    def sessions_between(self, start_session: date, end_session: date) -> tuple[date, ...]:
        sessions = self._calendar.sessions_in_range(
            pd.Timestamp(start_session),
            pd.Timestamp(end_session),
        )
        return tuple(pd.Timestamp(session).date() for session in sessions)

    def missing_sessions(self, observed_sessions: tuple[date, ...]) -> tuple[date, ...]:
        if not observed_sessions:
            return ()

        expected_sessions = self.sessions_between(observed_sessions[0], observed_sessions[-1])
        observed = set(observed_sessions)
        return tuple(session for session in expected_sessions if session not in observed)

    def is_session_complete(self, session: date, *, as_of: datetime) -> bool:
        as_of_utc = self.to_utc(as_of)
        if not self.is_session(session):
            return False

        close = pd.Timestamp(self._calendar.session_close(pd.Timestamp(session)))
        close = close.tz_localize(UTC) if close.tzinfo is None else close.tz_convert(UTC)
        close_time = cast(datetime, close.to_pydatetime())
        return as_of_utc >= close_time

    def to_utc(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            msg = "timestamp must be timezone-aware."
            raise ValueError(msg)
        return timestamp.astimezone(UTC)
