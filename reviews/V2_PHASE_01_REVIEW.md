# Version 2 Phase 1 Review

Starting main SHA: `3f5e3612bbf78b44845f3dedc24da35185a171f7`

Branch: `review/v2-phase-01-real-spy-data`

Final branch SHA: pending until commit; the final response records the pushed commit SHA.

Package version: `1.0.0`

## Scope Implemented

Implemented the Version 2 Phase 1 historical SPY daily-data foundation as an unreleased
review candidate:

- Explicit acquisition request validation.
- Separate market-data credentials.
- Alpaca historical market-data adapter.
- Raw sanitized provider snapshot storage.
- Canonical SPY daily CSV storage.
- XNYS session validation.
- Deterministic dataset manifests.
- SHA-256 source, canonical content, artifact, and manifest self-checksums.
- Deterministic dataset identity.
- Safe repository-relative storage and atomic writes.
- Local dataset verification command.
- Synthetic offline fixtures and tests.

## Provider Decision

Selected provider: Alpaca Market Data API, provisionally for Phase 1.

SDK and access method:

- `alpaca-py`
- `StockHistoricalDataClient`
- `/v2/stocks/bars`
- `feed`, `adjustment`, `sort=asc`, and pagination are explicit.

Provider decision record: `docs/V2_PHASE_01_PROVIDER_DECISION.md`.

## Provider Limitations

- Official support documentation does not prove SPY inception coverage.
- Alpaca support documentation says data is not available further back than 2016 and notes
  some missing early data points.
- SIP access can be subscription-limited.
- Alpaca API data must not be redistributed.
- Corporate-action evidence is limited to the provider adjustment policy in this
  implementation candidate; no separate corporate-action snapshot is acquired.
- No real-provider request was executed by Codex.

## Files Created

- `data/canonical/.gitkeep`
- `data/fixtures/v2_phase1_synthetic_alpaca_bars.json`
- `data/manifests/.gitkeep`
- `docs/V2_PHASE_01_PROVIDER_DECISION.md`
- `reviews/V2_PHASE_01_REVIEW.md`
- `src/spy_market_agent/market_data/acquisition.py`
- `src/spy_market_agent/market_data/alpaca_provider.py`
- `src/spy_market_agent/market_data/canonicalization.py`
- `src/spy_market_agent/market_data/cli.py`
- `src/spy_market_agent/market_data/errors.py`
- `src/spy_market_agent/market_data/manifest.py`
- `src/spy_market_agent/market_data/pipeline.py`
- `src/spy_market_agent/market_data/storage.py`
- `tests/integration/test_v2_phase1_acquisition_flow.py`
- `tests/unit/test_v2_phase1_market_data.py`

## Files Modified

- `.env.example`
- `.gitignore`
- `CHANGELOG.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/REPRODUCIBILITY.md`
- `docs/SECURITY_AND_SAFETY.md`
- `docs/V2_PHASE_01_REAL_SPY_DATA_SPEC.md`
- `docs/WORKFLOWS.md`
- `src/spy_market_agent/config/settings.py`
- `src/spy_market_agent/market_data/__init__.py`

## Storage Formats

Raw snapshot:

- UTF-8 JSON.
- Sorted keys.
- Compact separators.
- No NaN or Infinity.
- Terminal newline.
- Sanitized request metadata, provider identity, raw bar pages, pagination metadata, and
  retrieval timestamp.
- No credentials or authorization headers.

Canonical data:

- UTF-8 CSV.
- Fixed column order.
- ISO session dates.
- Deterministic decimal text.
- Integer-compatible volume.
- Ascending XNYS sessions.
- Terminal newline.

Manifest:

- UTF-8 deterministic JSON.
- Dataset identity, provider identity, requested and actual ranges, row counts, session
  summary, checksums, lineage, dependency versions, licensing classification, and generated
  relative file locations.

## Checksum Definitions

- Source checksum: SHA-256 over stable sanitized raw provider content, request parameters,
  provider identity, pagination metadata, and corporate-action evidence; retrieval timestamp
  is excluded.
- Canonical content checksum: SHA-256 over canonical rows, schema version, provider, feed,
  timeframe, adjustment mode, and corporate-action policy; local paths and derived lineage
  identifiers are excluded.
- Artifact checksum: SHA-256 over complete written raw or canonical artifact bytes.
- Manifest self-checksum: SHA-256 over the manifest with `manifest_artifact_checksum` unset.

## Dataset Identity

Dataset IDs are deterministic and derived from:

- symbol
- provider
- feed
- timeframe
- adjustment mode
- requested date range
- canonical schema version
- canonical content checksum
- corporate-action policy identifier

They are not derived from wall-clock time, random UUIDs, local absolute paths, usernames, or
package version.

## Security Controls

- Market-data credentials are separate from paper-trading credentials.
- Credentials are not accepted in CLI arguments.
- Provider exceptions are redacted.
- Imports, `--help`, invalid CLI input, missing acknowledgement, and missing credentials do
  not construct an Alpaca client.
- API and dashboard startup do not acquire market data.
- Storage rejects absolute roots, `..` traversal, source/doc/test/Git directories, symlink
  artifact paths, existing conflicts, and checksum mismatches.
- Generated provider data is ignored under `data/raw/`, `data/canonical/`, and
  `data/manifests/`.

## Test Categories

- Request validation.
- Credential separation.
- Settings redaction.
- Provider parameter mapping.
- Pagination.
- Bounded retry behavior.
- Error mapping and redaction.
- Canonical schema conversion.
- Numeric normalization.
- XNYS session validation.
- Incomplete-session rejection.
- Adjustment-mode isolation.
- Manifest construction.
- Deterministic serialization and checksums.
- Dataset identity.
- Safe paths and symlink rejection.
- Atomic write and idempotent existing-data behavior.
- Existing conflict rejection.
- CLI help, invalid-input, missing-acknowledgement, and missing-credential behavior.
- Fake-provider integration flow.
- Corrupted artifact rejection.
- Import/startup side-effect protection.

## Tests Deliberately Not Run

- Real Alpaca provider network smoke test.

Reason: the task explicitly says not to run it automatically. It requires owner credentials,
explicit opt-in, provider terms review, an isolated ignored output directory, and a narrow
completed historical range.

## Real Alpaca Request

No real Alpaca request was executed.

## Remaining Acceptance Items

- Owner review of this implementation branch.
- Owner-run controlled real-provider smoke test with market-data credentials only.
- Confirmation of account-specific Alpaca coverage, subscription, and licensing constraints.
- Final release-preparation correction that sets package/runtime version to `2.0.0a1` only
  after Phase 1 acceptance criteria pass.
- Merge to `main`, final verification on `main`, and only then optional creation of
  `v2.0.0-alpha.1`.

## Verification Results

- `python -m pip install -e ".[dev]"`: passed.
- `pytest --cov-fail-under=85`: 945 passed, 85.21% coverage.
- `pytest tests/unit -q`: passed; 915 unit tests collected.
- `pytest tests/integration -q`: 30 passed.
- `pytest -W error::FutureWarning`: 945 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.
- `mypy src tests`: passed.
- `git diff --check`: passed.
- `python -c "import importlib.metadata as m; import spy_market_agent; print(m.version('spy-market-agent'), spy_market_agent.__version__)"`:
  `1.0.0 1.0.0`.

- `pytest tests/unit/test_v2_phase1_market_data.py tests/integration/test_v2_phase1_acquisition_flow.py -q`:
  51 passed.

Collection count checks:

- Unit tests: 915.
- Integration tests: 30.
- Targeted Phase 1 tests: 51.

## Explicit Confirmations

- No model changed.
- No model was trained.
- No benchmark was run.
- No API write route was added.
- No dashboard execution control was added.
- No paper-order behavior changed.
- No trading client was contacted.
- No live support was added.
- No real market dataset was committed.
- No secret was committed.
- Package version remains `1.0.0`.
- No Git tag was created.
