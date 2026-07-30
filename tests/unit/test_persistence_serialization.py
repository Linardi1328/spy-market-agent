from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from spy_market_agent.persistence import (
    PersistenceInputError,
    PersistenceIntegrityError,
)
from spy_market_agent.persistence.serialization import (
    JsonValue,
    bool_to_int,
    canonical_json_dumps,
    canonical_json_loads,
    date_to_text,
    datetime_to_text,
    decimal_to_text,
    finite_float_for_storage,
    int_to_bool,
    require_run_id,
    text_to_date,
    text_to_datetime,
    text_to_decimal,
    validate_checksum,
)


def test_canonical_date_datetime_decimal_and_boolean_serialization() -> None:
    timestamp = datetime(2025, 1, 2, 7, 30, tzinfo=UTC)

    assert date_to_text(date(2025, 1, 2)) == "2025-01-02"
    assert text_to_date("2025-01-02") == date(2025, 1, 2)
    assert datetime_to_text(timestamp) == "2025-01-02T07:30:00Z"
    assert text_to_datetime("2025-01-02T07:30:00Z") == timestamp.astimezone(UTC)
    assert decimal_to_text(Decimal("123.4500")) == "123.4500"
    assert text_to_decimal("123.4500") == Decimal("123.4500")
    assert bool_to_int(True) == 1
    assert bool_to_int(False) == 0
    assert int_to_bool(1) is True
    assert int_to_bool(0) is False


def test_canonical_json_is_deterministic_and_rejects_non_finite_values() -> None:
    left: JsonValue = {"b": [2, 1], "a": {"z": "value"}}
    right: JsonValue = {"a": {"z": "value"}, "b": [2, 1]}

    assert canonical_json_dumps(left) == canonical_json_dumps(right)
    assert canonical_json_dumps(left) == '{"a":{"z":"value"},"b":[2,1]}'
    with pytest.raises(PersistenceInputError, match="canonical JSON"):
        canonical_json_dumps({"bad": float("nan")})
    with pytest.raises(PersistenceIntegrityError, match="finite"):
        finite_float_for_storage(float("inf"), field_name="bad_value")
    with pytest.raises(PersistenceIntegrityError, match="canonical JSON"):
        canonical_json_loads("NaN")
    with pytest.raises(PersistenceIntegrityError, match="canonical JSON"):
        canonical_json_loads("Infinity")
    with pytest.raises(PersistenceIntegrityError, match="canonical JSON"):
        canonical_json_loads("-Infinity")


@pytest.mark.parametrize(
    "payload",
    [
        "1e999",
        "-1e999",
        "[1e999]",
        '{"value":1e999}',
        '{"outer":[{"inner":{"value":1e999}}]}',
    ],
)
def test_canonical_json_loads_rejects_overflowing_numeric_values(payload: str) -> None:
    with pytest.raises(PersistenceIntegrityError, match="canonical JSON"):
        canonical_json_loads(payload)


def test_canonical_json_loads_preserves_finite_json_values() -> None:
    assert canonical_json_loads("1e10") == 10_000_000_000.0
    assert canonical_json_loads('{"a":[1,2.5,true,null],"b":{"c":"value"}}') == {
        "a": [1, 2.5, True, None],
        "b": {"c": "value"},
    }
    assert canonical_json_loads("[1,2,3]") == [1, 2, 3]


def test_checksum_validation_requires_lowercase_sha256() -> None:
    checksum = "a" * 64

    assert validate_checksum(checksum) == checksum
    with pytest.raises(PersistenceIntegrityError, match="SHA-256"):
        validate_checksum("A" * 64)


@pytest.mark.parametrize(
    "run_id",
    [
        "a",
        "A1",
        "run.01_test-02",
        "a" * 128,
    ],
)
def test_run_id_contract_accepts_url_safe_identifiers(run_id: str) -> None:
    assert require_run_id(run_id) == run_id


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "   ",
        " leading",
        "trailing ",
        "internal space",
        "bad/slash",
        "bad\\slash",
        "bad%percent",
        "bad?query",
        "bad#hash",
        "bad&amp",
        "bad:colon",
        "%2Fencoded",
        "a" * 129,
    ],
)
def test_run_id_contract_rejects_unsafe_identifiers_without_normalizing(run_id: str) -> None:
    with pytest.raises(PersistenceInputError, match="run_id"):
        require_run_id(run_id)
