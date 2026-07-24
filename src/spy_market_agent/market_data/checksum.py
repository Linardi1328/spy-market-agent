from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, cast

import pandas as pd

from spy_market_agent.market_data.models import CANONICAL_COLUMNS

CHECKSUM_VERSION = "canonical-daily-ohlcv-v1-sha256"


def _session_to_iso(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()

    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        msg = "session cannot be missing for checksum generation."
        raise ValueError(msg)
    session = cast(date, timestamp.date())
    return session.isoformat()


def _price_to_stable_string(value: Any) -> str:
    numeric = float(value)
    return format(numeric, ".12g")


def _volume_to_stable_string(value: Any) -> str:
    return str(int(value))


def compute_market_data_checksum(frame: pd.DataFrame) -> str:
    """Compute a deterministic SHA-256 digest for canonical daily OHLCV data.

    Serialization uses canonical column order, ISO session dates, stable decimal strings
    for OHLC values, integer strings for volume, and current row order. Volatile timestamps,
    local paths, provider credentials, and metadata are intentionally excluded.
    """

    if tuple(frame.columns) != CANONICAL_COLUMNS:
        msg = "checksum requires canonical column order."
        raise ValueError(msg)

    rows: list[list[str]] = []
    for record in frame.itertuples(index=False, name=None):
        rows.append(
            [
                _session_to_iso(record[0]),
                _price_to_stable_string(record[1]),
                _price_to_stable_string(record[2]),
                _price_to_stable_string(record[3]),
                _price_to_stable_string(record[4]),
                _volume_to_stable_string(record[5]),
            ]
        )

    payload = {
        "version": CHECKSUM_VERSION,
        "columns": list(CANONICAL_COLUMNS),
        "rows": rows,
    }
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
