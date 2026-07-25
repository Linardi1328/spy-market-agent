from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pandas as pd

from spy_market_agent.datasets.models import (
    EXIT_OFFSET_SESSIONS,
    LABEL_COLUMNS,
    LABEL_SCHEMA_VERSION,
    SupervisedDataset,
    SupervisedDatasetMetadata,
)
from spy_market_agent.datasets.splits import (
    ChronologicalPartitions,
    ChronologicalSplitSpec,
    split_supervised_dataset,
)
from spy_market_agent.features.models import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION
from spy_market_agent.market_data.calendar import XNYSCalendar
from spy_market_agent.market_data.models import SCHEMA_VERSION as MARKET_DATA_SCHEMA_VERSION

CREATED_AT = datetime(2025, 1, 2, 12, 0, tzinfo=UTC)
SOURCE_CHECKSUM = "1" * 64


def target_for_index(index: int) -> int:
    return 1 if index % 6 in {0, 1, 2} else 0


def make_sessions(row_count: int = 150) -> list[date]:
    return list(XNYSCalendar().sessions_between(date(2024, 1, 2), date(2024, 12, 31)))[:row_count]


def make_supervised_dataset(row_count: int = 150) -> SupervisedDataset:
    sessions = make_sessions(row_count)
    label_count = row_count - EXIT_OFFSET_SESSIONS
    feature_records: list[dict[str, object]] = []
    label_records: list[dict[str, object]] = []
    for index in range(label_count):
        target = target_for_index(index)
        direction = 1.0 if target == 1 else -1.0
        feature_record: dict[str, object] = {"session": sessions[index]}
        for column_index, column in enumerate(FEATURE_COLUMNS, start=1):
            feature_record[column] = (
                direction * (0.10 + column_index * 0.01)
                + math.sin((index + column_index) * 0.17) * 0.015
                + index * 0.0003
            )
        feature_records.append(feature_record)
        net_forward_return = 0.02 if target == 1 else -0.02
        label_records.append(
            {
                "session": sessions[index],
                "entry_session": sessions[index + 1],
                "exit_session": sessions[index + EXIT_OFFSET_SESSIONS],
                "gross_forward_return": net_forward_return,
                "net_forward_return": net_forward_return,
                "target": target,
            }
        )

    features = pd.DataFrame.from_records(
        feature_records,
        columns=["session", *FEATURE_COLUMNS],
    )
    labels = pd.DataFrame.from_records(label_records, columns=list(LABEL_COLUMNS))
    for column in FEATURE_COLUMNS:
        features[column] = features[column].astype("float64")
    labels["gross_forward_return"] = labels["gross_forward_return"].astype("float64")
    labels["net_forward_return"] = labels["net_forward_return"].astype("float64")
    labels["target"] = labels["target"].astype("int64")
    metadata = SupervisedDatasetMetadata(
        source_market_data_checksum=SOURCE_CHECKSUM,
        source_schema_version=MARKET_DATA_SCHEMA_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        label_schema_version=LABEL_SCHEMA_VERSION,
        feature_columns=FEATURE_COLUMNS,
        row_count=len(features),
        first_session=features.iloc[0]["session"],
        last_session=features.iloc[-1]["session"],
        created_at=CREATED_AT,
    )
    return SupervisedDataset(features=features, labels=labels, metadata=metadata)


def make_split_spec(sessions: list[date]) -> ChronologicalSplitSpec:
    return ChronologicalSplitSpec(
        train_start_session=sessions[0],
        train_end_session=sessions[41],
        validation_start_session=sessions[48],
        validation_end_session=sessions[89],
        test_start_session=sessions[96],
        test_end_session=sessions[149],
    )


def make_partitions() -> ChronologicalPartitions:
    sessions = make_sessions()
    return split_supervised_dataset(make_supervised_dataset(), make_split_spec(sessions))
