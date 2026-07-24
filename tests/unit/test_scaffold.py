from __future__ import annotations

import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import spy_market_agent

ROOT = Path(__file__).resolve().parents[2]


def _allows_version(requirement: str, version: tuple[int, int]) -> bool:
    major, minor = version

    for raw_constraint in requirement.split(","):
        constraint = raw_constraint.strip()
        if constraint.startswith(">="):
            minimum = tuple(int(part) for part in constraint[2:].split("."))
            if (major, minor) < minimum:
                return False
        elif constraint.startswith("<"):
            maximum = tuple(int(part) for part in constraint[1:].split("."))
            if (major, minor) >= maximum:
                return False
        else:
            msg = f"Unsupported version constraint in test: {constraint}"
            raise AssertionError(msg)

    return True


def test_package_can_be_imported() -> None:
    assert spy_market_agent is not None


def test_package_version_is_non_empty_string() -> None:
    assert isinstance(spy_market_agent.__version__, str)
    assert spy_market_agent.__version__


def test_package_version_matches_installed_metadata() -> None:
    assert spy_market_agent.__version__ == version("spy-market-agent")


def test_required_top_level_documentation_files_exist() -> None:
    assert (ROOT / "PROJECT_SPEC.md").is_file()
    assert (ROOT / "AGENTS.md").is_file()
    assert (ROOT / "README.md").is_file()


def test_real_env_file_is_not_tracked_or_required() -> None:
    assert (ROOT / ".env.example").is_file()

    if not (ROOT / ".git").exists():
        return

    result = subprocess.run(
        ["git", "ls-files", "--", ".env"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    assert result.stdout == ""


def test_declared_python_version_range_supports_only_python_3_12() -> None:
    with (ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    requires_python = pyproject["project"]["requires-python"]

    assert _allows_version(requires_python, (3, 12))
    assert not _allows_version(requires_python, (3, 13))
    assert not _allows_version(requires_python, (sys.version_info.major, 14))
