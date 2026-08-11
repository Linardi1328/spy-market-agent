# Security and Safety

## Threat Model

Protected assets include local credentials, account identifiers, paper-order intent, model and
backtest lineage, SQLite audit records, and the integrity of safety gates. Main risks are
credential leakage, accidental live trading, model-to-broker bypass, duplicate paper orders,
stale signals, corrupted persisted artifacts, and user interfaces mutating execution state.

## Credential Handling

- Credentials are read from runtime configuration only.
- `.env.example` contains placeholders only.
- `Settings` uses secret-aware fields for Alpaca keys.
- Display-safe settings expose only credential-presence booleans.
- Full account IDs are fingerprinted before persistence.
- Logs, API responses, dashboard views, tests, and review records must not expose secrets.
- Version 2 Phase 1 market-data credentials are separate from paper-trading credentials:
  `ALPACA_MARKET_DATA_API_KEY` and `ALPACA_MARKET_DATA_SECRET_KEY`.
- The Phase 1 acquisition CLI never accepts credentials as command-line arguments and never
  falls back to `ALPACA_API_KEY` or `ALPACA_SECRET_KEY`.

## Paper-Only Enforcement

- `EXECUTION_MODE` may only be `paper`.
- Live mode must raise at settings or execution boundaries.
- The project has no public `paper=False` client path.
- `AlpacaPaperBroker` constructs `TradingClient(..., paper=True)` only when explicitly
  instantiated.
- The only approved endpoint identity is `https://paper-api.alpaca.markets`.
- Broker environment verification must report paper mode before any submission.

## Approval Binding

Paper submission requires a `PaperOrderApproval` where:

- `approved` is exactly `True`
- signal ID matches the instruction
- client-order ID matches the instruction
- approval ID is unique
- approval timestamp is after instruction creation
- approval is not from the future at execution time
- approval has not expired
- instruction fingerprint matches exactly

The fingerprint is a SHA-256 digest over versioned instruction, proposed-order, risk-decision,
cost, session, ID, and timestamp data.

## Kill Switches

Version 1 uses two independent kill switches:

- configuration kill switch: `PAPER_EXECUTION_KILL_SWITCH`, default `true`
- durable SQLite kill switch: stored in `paper_execution_control`, default engaged

The effective state is the logical OR. Both must be deliberately disengaged before an
explicit paper submission can proceed. Durable disengagement requires the exact confirmation
token `DISENGAGE_PAPER_EXECUTION_KILL_SWITCH` and a nonblank reason. API and dashboard views
cannot change either switch.

## Execution-Time Safety Gates

Before broker submission, the service checks:

- local configuration and credentials
- broker paper environment and endpoint identity
- active USD account with finite nonnegative balances
- account configuration with no shorting, margin multiplier 1, and no trade suspension
- regular market hours
- instruction execution session and exclusive expiration boundary
- SPY asset active, tradable, and US equity
- no unsupported positions
- no conflicting SPY open orders
- independent execution-time risk approval
- durable ID reservation
- broker lookup by `client_order_id`
- refreshed broker clock
- final durable kill-switch state

`PAPER_EXECUTION_REQUIRE_MARKET_OPEN=false` is rejected. Extended-hours orders are not
supported.

## Duplicate and Concurrency Controls

The SQLite ledger enforces uniqueness for:

- `signal_id`
- `client_order_id`
- `approval_id`
- `(symbol, execution_session)`

Version 1 permits at most one SPY paper-execution attempt for a given execution session.
Reserved, accepted, broker-existing, reconciled, rejected, blocked, and unknown attempts all
consume that session. This strict rule prevents pyramiding or conflicting same-session
submissions.

## Unknown Submission Handling

The service records `submission_unknown` when a broker submit may have started but the local
outcome is uncertain. Examples include timeout, cancellation, connection loss, malformed
post-submit response, contradictory response, or broker acceptance followed by local ledger
failure.

Unknown submissions retain IDs and session reservations. They are not retried automatically.

## Reconciliation Rules

Reconciliation is explicit lookup-only by `client_order_id`. It never submits. Broker lookup
returns broker-observable order fields only. Local signal ID, approval ID, and fingerprint
lineage come from the persisted local attempt, not from broker fields.

Mismatched broker snapshots fail closed and keep the attempt unresolved.

## Database Integrity

SQLite initialization is explicit. Every connection enables foreign keys. The schema version
and required paper-execution unique index are validated on read. Persisted research artifacts
and paper-execution records are reconstructed through typed domain objects and project-owned
validation paths.

Unsupported future schema versions, corrupted rows, non-finite values, malformed IDs,
invalid booleans, missing required rows, checksum mismatches, and invalid attempt transitions
fail safely with sanitized project errors.

## API and Dashboard Boundaries

FastAPI exposes only GET application routes. Streamlit has no approve, submit, reconcile,
retry, enable, disable, cancel, replace, liquidation, or kill-switch controls. API and
dashboard paths do not construct Alpaca clients and do not initialize or migrate SQLite.

The Version 2 Phase 1 acquisition path is CLI-only and explicit. FastAPI startup, Streamlit
startup, dashboard rendering, package imports, and test collection do not acquire market
data, construct a market-data client, or write raw/canonical/manifest artifacts.

The Version 2 Phase 2 benchmark path is also CLI-only and explicit. Benchmark commands use a
Phase 1 manifest and owner-provided feed-decision records; they do not make network
requests, require credentials, construct an Alpaca market-data client, construct a
`TradingClient`, initialize SQLite, submit orders, or expose final-test row-level labels
before explicit final-test access acknowledgement. Generated benchmark artifacts are ignored
under `artifacts/benchmarks/`.

Phase 2 benchmark verification is a deep offline semantic check. It validates artifact
schemas, recomputes benchmark identity, re-verifies the referenced Phase 1 dataset,
reconstructs features, labels, splits, eligibility, validation artifacts, final locks, and
completed final-test relationships, and rejects tampering even when `artifact_index.json`
hashes were recomputed. Critical stages fail closed when current Git, Python, package, or
dependency lineage differs from `benchmark_lock.json`.

`final_test_access.json` is immutable evidence that final-test access began and is written
before row-level final-test labels are loaded. It is not overwritten with completion status.
Successful Stage B completion is recorded separately in `final_test_completion.json`. A
failed first access preserves the started record and requires explicit operator review before
any non-audit re-attempt; audit replay never creates a new access record or overwrites
accepted final artifacts.

The Version 2 Phase 3 research path is accepted and released as `v2.0.0-alpha.3` after PR
#24 merged the approved framework, PR #25 merged the development research runner, owner
development testing completed locally, and Alpha 3 release preparation was tagged. Its
package-local runner must not load Phase 2
final-test row-level labels, predictions, strategy rows, fills, or generated benchmark JSON
for tuning. It also must not reconstruct Phase 2 final-test row-level labels indirectly from
the parent canonical dataset: the development runner reconstructs the frozen Phase 2 split
boundary, truncates the research slice before label construction, and fails closed if
training, assessment, calibration, diagnostics, or selection sessions intersect Phase 2
final-test prediction sessions. Phase 3 generated real-data research artifacts remain
ignored under `artifacts/research/<experiment_id>/`, and tracked acceptance evidence is
sanitized aggregate documentation only. The Phase 3 CLI is manual, offline after data
acquisition, credential-free, broker-free, and unable to submit paper or live orders.
Protected evaluation, strategy optimization, production paper operation, and live trading
remain unauthorized. The Phase 3 scientific outcome was `NO CANDIDATE PROMOTION`, so no
model is approved for shadow or paper operation.

The Version 2 Phase 4 shadow scaffold is governed by
`docs/V2_PHASE_04_REAL_TIME_SHADOW_MODE_SPEC.md`. It is infrastructure-first and starts in
`observation_only_no_model` mode. It may evaluate synthetic or local session readiness,
freshness, completeness, deterministic run identity, duplicate-run state, model-admission
state, and monitoring state. It must not generate model predictions from real data,
construct model-based `LONG` or `CASH` proposals, submit orders, create risk approvals,
initialize paper execution, construct Alpaca `TradingClient`, use broker credentials, expose
API write routes, add dashboard execution controls, or start a scheduler. Model-connected
shadow inference is locked with machine-readable status `blocked_no_approved_model` until a
future separately approved immutable model-admission record exists. Phase 5 production paper
operation and live trading remain unauthorized.

## Historical Market-Data Safety

Phase 1 market-data acquisition safeguards:

- SPY only.
- Daily bars only.
- Explicit provider, feed, adjustment mode, date range, and provider-terms acknowledgement.
- Credentials read only from market-data environment variables.
- No trading client, order method, paper endpoint, live endpoint, API write route, dashboard
  control, model training, or backtest execution.
- Bounded retries for transient provider failures only.
- No retry for authentication, authorization, malformed data, invalid requests, checksum
  mismatch, or session validation failure.
- Safe repository-relative data root.
- Protection against `..` traversal, absolute-path escape, source/doc/test/Git directories,
  symlink artifact paths, and existing conflicting artifacts.
- Atomic temporary-file writes followed by checksum verification and `Path.replace`.
- Local-only ignored storage under `data/raw/`, `data/canonical/`, and `data/manifests/`.
- Provider data is not redistributed and must not be committed.
- Synthetic fixtures are visibly identified under `data/fixtures/`.

If market data is missing, out of order, duplicated, outside XNYS sessions, future-dated,
incomplete, non-finite, non-positive, negative-volume, or OHLC-inconsistent, acquisition
fails closed.

## Dependency and Warning Policy

Dependencies are constrained in `pyproject.toml`. Unexpected test warnings fail by default.
Allowed warning filters are exact documented upstream warnings only. Broad suppressions should
not be added to hide project warnings.

## Incident Response Checklist

1. Stop using any affected local database.
2. Engage the configuration kill switch.
3. Engage the durable SQLite kill switch if the database is trusted enough to open safely.
4. Preserve the SQLite file for audit if it may contain an unresolved attempt.
5. Inspect `paper_execution_attempts` and `paper_execution_events` read-only.
6. For `submission_unknown`, reconcile by broker `client_order_id` using lookup only.
7. Rotate any potentially exposed credentials outside the repository.
8. Remove generated databases, logs, screenshots, or reports containing private information
   before committing.
9. Run the full verification suite and safety searches before resuming work.

## Known Residual Risks

- Paper fills can differ from historical backtest assumptions and from live fills.
- A kill switch engaged after the final pre-submit check cannot cancel an already in-flight
  broker request.
- Reconciliation depends on broker lookup availability.
- SQLite is local-file persistence, not a multi-user production database.
- Exact reproducibility can vary when dependency versions differ.
- No authentication, deployment hardening, scheduler, or live-trading support exists in
  Version 1.
