# Reproducibility

## Python Version

Use Python 3.12. Project metadata requires:

```text
>=3.12,<3.13
```

## Clean Environment Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The repository does not include a lock file, so exact transitive dependency versions can
differ across machines. Reproducibility metadata is recorded in persisted research artifacts
where available, but byte-for-byte reproduction is not guaranteed when dependency versions
change.

## Verification Commands

```bash
python -m pip install -e ".[dev]"
pytest --cov-fail-under=85
pytest tests/unit -q
pytest tests/integration -q
ruff check .
ruff format --check .
mypy src tests
python -c "import spy_market_agent; print(spy_market_agent.__version__)"
```

Coverage is branch-aware and must remain at least 85% for the full suite.

## Warning Policy

`pyproject.toml` configures Pytest to treat unexpected warnings as errors. The allowed
warning filters are exact upstream dependency warnings by category, message, and module.
New project warnings or broad warning suppressions should be treated as release blockers.

## Deterministic Inputs

Version 1 uses deterministic random seeds where applicable. The default modeling seed is
`42`, and fixed model parameter snapshots preserve the semantic logistic-regression lineage,
including `classifier.penalty="l2"`.

No real SPY dataset is committed. Tests use deterministic synthetic or in-memory data.
External data used by a developer must be validated, checksummed, and persisted locally before
API or dashboard inspection.

## Checksums and Schema Versions

Validated data and downstream artifacts retain explicit schema and checksum lineage:

- market-data schema: `spy-daily-ohlcv-v1`
- feature schema: `spy-daily-features-v1`
- label schema: `spy-open-t1-to-open-t6-net-positive-v1`
- model schema: `spy-binary-models-v1`
- strategy schema: `spy-long-cash-strategy-v1`
- risk schema: `spy-long-only-risk-v1`
- backtest schema: `spy-daily-next-open-backtest-v1`
- paper-execution schema: `spy-paper-execution-v1`
- SQLite schema: `spy-sqlite-persistence-v2`

Market-data checksums are deterministic over canonical rows, column order, session order,
prices, and volume. Backtest results also retain source market data and execution-price
lineage so persisted artifacts can be reconstructed and revalidated.

## Split Specifications

Chronological splits are explicit date-boundary objects. They do not shuffle observations.
Rows are included only when the feature session and the label exit session fit inside the
partition boundary. The final test partition is not used for model selection.

## Git and Dependency Lineage

Persisted model evaluations and backtests can record Git commit hash, Python version, and
dependency versions through `RuntimeSnapshot`. This metadata helps explain when an artifact
was produced and what package versions were present.

## SQLite Initialization

SQLite initialization is explicit and idempotent:

```bash
python -c "from spy_market_agent.persistence import initialize_database; initialize_database('./spy_market_agent.sqlite3')"
```

Imports, API startup, and dashboard startup do not initialize or migrate SQLite files. Read
paths fail safely when a database is unavailable, uninitialized, corrupted, or on an unsupported
future schema.

## Reconstructing Persisted Artifacts

`SQLiteArtifactRepository` supports loading persisted market-data batches, final model
evaluations, and backtest results. Load paths reconstruct domain objects and rerun the
existing validation, checksum, schema, lineage, accounting, metric, and risk checks instead of
trusting stored rows blindly.

`SQLitePaperExecutionRepository` reconstructs local paper-execution control state, attempts,
and events from the durable ledger. It validates schema version, IDs, checksums, attempt
states, booleans, timestamps, and the required symbol/session uniqueness index.

## Limitations

- No lock file is committed, so dependency resolution can vary.
- No committed real SPY dataset exists.
- Historical adjusted-price backtests approximate return distributions and corporate-action
  effects; they do not guarantee executable fills.
- Classification metrics and backtests are diagnostics only and are not evidence of
  profitability.
