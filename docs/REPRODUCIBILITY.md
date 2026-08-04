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
pytest -W error::FutureWarning
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

## Version 2 Phase 1 Data Foundation

**Accepted for alpha release preparation:** Phase 1 adds explicit historical SPY daily-data
acquisition. Normal verification remains offline and does not require market-data
credentials.

Example explicit acquisition command:

```bash
python -m spy_market_agent.market_data.cli acquire \
  --provider alpaca \
  --symbol SPY \
  --start 2016-01-04 \
  --end 2016-01-08 \
  --timeframe 1Day \
  --feed sip \
  --adjustment all \
  --data-root ./data \
  --acknowledge-provider-terms
```

Required environment variables for real acquisition:

```bash
export ALPACA_MARKET_DATA_API_KEY=...
export ALPACA_MARKET_DATA_SECRET_KEY=...
export ALPACA_MARKET_DATA_FEED=sip
export MARKET_DATA_ROOT=./data
export MARKET_DATA_MAX_RETRIES=3
export MARKET_DATA_TIMEOUT_SECONDS=30
```

Do not put credentials in shell history, committed files, manifests, or command-line
arguments. The normal test suite uses synthetic data and does not contact Alpaca.
`MARKET_DATA_TIMEOUT_SECONDS` is enforced at the actual Alpaca SDK HTTP request boundary; it
is not merely retry sleep. `MARKET_DATA_MAX_RETRIES` controls retry count separately.

Deterministic artifact rules:

- Raw snapshots are UTF-8 JSON with sorted keys, compact separators, no NaN/Infinity, and a
  trailing newline.
- Canonical bars are UTF-8 CSV with fixed column order, LF line endings, ISO session dates,
  deterministic decimal text, integer-compatible volume, and a trailing newline.
- Manifests are UTF-8 JSON with sorted keys, compact separators, no credentials, and recorded
  version and dependency lineage.

Checksum definitions:

- Source checksum: SHA-256 over stable sanitized raw provider content, request parameters,
  provider identity, pagination metadata, and corporate-action evidence. Volatile retrieval
  timestamp is excluded.
- Canonical content checksum: SHA-256 over canonical rows, canonical schema version,
  provider, feed, timeframe, adjustment mode, and corporate-action policy. Derived lineage
  identifiers and local paths are excluded.
- Artifact checksum: SHA-256 over the complete written raw or canonical artifact bytes.
- Manifest self-checksum: SHA-256 over the manifest with its self-checksum field unset.

Dataset identity:

```text
symbol
+ provider
+ feed
+ timeframe
+ adjustment mode
+ requested date range
+ canonical schema version
+ canonical content checksum
+ corporate-action policy identifier
```

The dataset ID is not derived from clock time, random UUIDs, local absolute paths, usernames,
or the package version.

Idempotent behavior:

- Repeating acquisition with unchanged provider content produces the same canonical content
  checksum and dataset ID.
- Existing matching artifacts are reused without destructive rewrite.
- Existing conflicting artifacts fail closed.
- Changing provider content, provider, feed, date range, schema, or adjustment mode changes
  the dataset identity or fails explicitly.
- Raw, canonical, and manifest writes are handled as one multi-artifact operation. If a
  later artifact fails after an earlier artifact was newly created by the same attempt, the
  newly created files are removed best-effort while preserving valid matching artifacts that
  existed before the attempt.
- Acquisition captures the current timestamp once and reuses it for provider snapshot
  timestamping, incomplete-session validation, manifest reasoning, and lineage decisions.

Verify an existing local dataset without network access:

```bash
python -m spy_market_agent.market_data.cli verify \
  --manifest data/manifests/alpaca/SPY/1Day/sip/all/DATASET_ID.manifest.json \
  --data-root ./data
```

The manifest path is an example shape. Replace `DATASET_ID` with a real local ignored
dataset ID.

Verification is a deep offline reconstruction, not only a byte-hash check. It loads and
validates the manifest, verifies the manifest self-checksum, resolves paths under the
approved data root, verifies raw and canonical artifact hashes, parses the sanitized raw JSON
snapshot, parses canonical CSV into typed daily bars, recomputes source and canonical content
checksums, recomputes the dataset ID, confirms filenames and recorded generated paths, checks
row count and first/last sessions, reruns OHLCV and XNYS validation from the recorded
retrieval timestamp, and fails closed on mismatches.

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
