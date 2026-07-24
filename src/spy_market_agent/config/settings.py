from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _require_value(value: str, *, expected: str, field_name: str) -> str:
    if value != expected:
        msg = f"{field_name} must be {expected!r} for Version 1."
        raise ValueError(msg)
    return value


class Settings(BaseSettings):
    """Typed application settings.

    Settings may be supplied explicitly, through environment variables, or through a local
    `.env` file. Instantiating this class never submits orders, imports execution adapters,
    or requires broker credentials.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    environment: str = "development"
    execution_mode: str = "paper"
    enable_paper_execution: bool = False
    dry_run: bool = True
    initial_capital_usd: Decimal = Field(default=Decimal("10000"), gt=Decimal("0"))
    database_url: str = "sqlite:///./spy_market_agent.db"
    market_symbol: str = "SPY"
    market_timeframe: str = "1Day"
    exchange_calendar: str = "XNYS"
    market_timezone: str = "America/New_York"
    adjustment_policy: str = "adjusted"
    alpaca_api_key: SecretStr | None = Field(default=None, repr=False)
    alpaca_secret_key: SecretStr | None = Field(default=None, repr=False)

    @field_validator("execution_mode")
    @classmethod
    def _validate_execution_mode(cls, value: str) -> str:
        return _require_value(value, expected="paper", field_name="execution_mode")

    @field_validator("market_symbol")
    @classmethod
    def _validate_market_symbol(cls, value: str) -> str:
        return _require_value(value, expected="SPY", field_name="market_symbol")

    @field_validator("market_timeframe")
    @classmethod
    def _validate_market_timeframe(cls, value: str) -> str:
        return _require_value(value, expected="1Day", field_name="market_timeframe")

    @field_validator("exchange_calendar")
    @classmethod
    def _validate_exchange_calendar(cls, value: str) -> str:
        return _require_value(value, expected="XNYS", field_name="exchange_calendar")

    @field_validator("market_timezone")
    @classmethod
    def _validate_market_timezone(cls, value: str) -> str:
        return _require_value(
            value,
            expected="America/New_York",
            field_name="market_timezone",
        )

    @field_validator("adjustment_policy")
    @classmethod
    def _validate_adjustment_policy(cls, value: str) -> str:
        return _require_value(value, expected="adjusted", field_name="adjustment_policy")

    @property
    def paper_order_submission_enabled(self) -> bool:
        """Whether future paper-order submission would be permitted by configuration only."""

        return self.execution_mode == "paper" and self.enable_paper_execution and not self.dry_run

    def display_safe_dict(self) -> dict[str, Any]:
        """Return settings suitable for display without revealing secret values."""

        safe_values = self.model_dump(mode="json")
        safe_values["database_url"] = _redact_url_userinfo(self.database_url)
        return safe_values


def load_settings() -> Settings:
    """Load settings without creating files or performing external actions."""

    return Settings()


def _redact_url_userinfo(url: str) -> str:
    parsed = urlsplit(url)
    if "@" not in parsed.netloc:
        return url

    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    netloc = f"***:***@{host}"
    return urlunsplit(
        SplitResult(
            scheme=parsed.scheme,
            netloc=netloc,
            path=parsed.path,
            query=parsed.query,
            fragment=parsed.fragment,
        )
    )
