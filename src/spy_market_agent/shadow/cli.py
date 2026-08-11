from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from spy_market_agent.market_data.errors import MarketDataAcquisitionError
from spy_market_agent.shadow.persistence import (
    ShadowPersistenceError,
    ShadowRunNotFoundError,
    ShadowSQLiteRepository,
)
from spy_market_agent.shadow.runner import (
    ShadowOperationalError,
    require_explicit_utc_datetime,
    run_observation,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run-observation":
        return _run_observation_command(args)
    if args.command == "show-run":
        return _show_run_command(args)
    parser.error("unsupported command")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m spy_market_agent.shadow.cli",
        description="Manual Phase 4 observation-only shadow operations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run-observation",
        help="Run one manual observation-only shadow readiness check.",
    )
    run_parser.add_argument("--manifest", required=True, type=Path)
    run_parser.add_argument("--data-root", required=True, type=Path)
    run_parser.add_argument("--shadow-db", required=True, type=Path)
    run_parser.add_argument("--session", required=True)
    run_parser.add_argument("--as-of", required=True)
    run_parser.add_argument("--provider-finalized", action="store_true")
    run_parser.add_argument("--provider-finalization-policy-id", required=True)

    show_parser = subparsers.add_parser(
        "show-run",
        help="Show one persisted shadow run without mutating state.",
    )
    show_parser.add_argument("--shadow-db", required=True, type=Path)
    show_parser.add_argument("--run-id", required=True)
    return parser


def _run_observation_command(args: argparse.Namespace) -> int:
    try:
        session = _parse_session(args.session)
        as_of = _parse_utc_timestamp(args.as_of)
        result = run_observation(
            manifest_path=args.manifest,
            data_root=args.data_root,
            shadow_db=args.shadow_db,
            session=session,
            as_of=as_of,
            provider_finalized=bool(args.provider_finalized),
            provider_finalization_policy_id=args.provider_finalization_policy_id,
        )
    except (
        MarketDataAcquisitionError,
        ShadowOperationalError,
        ShadowPersistenceError,
        ValueError,
    ) as exc:
        print("status=failed_closed")
        print(f"reason={getattr(exc, 'code', 'invalid_shadow_observation_request')}")
        return 1

    for line in result.sanitized_summary_lines(
        shadow_db_display=_display_path(args.shadow_db),
    ):
        print(line)
    return 0


def _show_run_command(args: argparse.Namespace) -> int:
    try:
        stored = ShadowSQLiteRepository(args.shadow_db).get_run(args.run_id)
    except ShadowRunNotFoundError as exc:
        print("status=not_found")
        print(f"reason={exc.code}")
        return 1
    except ShadowPersistenceError as exc:
        print("status=failed_closed")
        print(f"reason={exc.code}")
        return 1

    run = stored.run
    print(f"shadow_run_id={run.shadow_run_id}")
    print(f"mode={run.mode.value}")
    print(f"session={run.signal_session}")
    print(f"run_status={run.run_status.value}")
    print(f"freshness_status={run.freshness_status.value}")
    print(f"monitoring_status={run.monitoring_status.value}")
    print(f"model_gate_status={run.model_gate_status.value}")
    print(f"parent_dataset_id={run.parent_dataset_id}")
    print(f"canonical_dataset_checksum={run.canonical_dataset_checksum}")
    print(f"provider_finalization_policy_id={run.provider_finalization_policy_id}")
    print(f"created_at={run.created_at}")
    print(f"completed_at={run.completed_at or 'none'}")
    print("health_events=" + ",".join(event.event_code for event in stored.health_events))
    print("alerts=" + (",".join(alert.alert_code for alert in stored.alerts) or "none"))
    return 0


def _parse_session(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("session must use YYYY-MM-DD format.") from exc


def _parse_utc_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("as-of must be an ISO-8601 UTC datetime.") from exc
    return require_explicit_utc_datetime(parsed, field_name="as_of")


def _display_path(path: Path) -> str:
    if path.is_absolute():
        return path.name
    return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
