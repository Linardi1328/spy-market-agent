# Version 2 Phase 4 - Real-Time Shadow Mode Specification

Status: Active specification and infrastructure-first scaffolding

Target release identifier: `v2.0.0-beta.1`

Current implementation branch: `review/v2-phase-04-shadow-mode`

Current package/runtime version during specification/scaffolding: `2.0.0a3`

Version 2 Phase 3 is complete and released as `v2.0.0-alpha.3`. Its scientific outcome was
`NO CANDIDATE PROMOTION`. No Phase 3 model is approved for protected evaluation, shadow
operation, production paper operation, or live trading. Phase 4 may begin only as
infrastructure-first shadow-mode scaffolding under explicit owner authorization. It must not
reinterpret or bypass the Phase 3 model rejection result.

## 1. Purpose

Phase 4 defines and begins the shadow-mode operating layer for SPY daily market
intelligence. The goal is to build calendar-aware, reproducible, observable infrastructure
that can later run approved model inference against newly completed daily sessions without
submitting orders.

This first Phase 4 substage is not a complete production shadow system. It establishes
terminology, governance, safety boundaries, deterministic identities, model-admission locks,
freshness checks, scheduling policy functions, monitoring state, alert concepts, persistence
design, and synthetic tests.

## 2. Background

Version 1 created the SPY daily research, backtesting, read-only API/dashboard, and
paper-only execution safeguards. Version 2 Phase 1 added verified real SPY daily data
acquisition and manifests. Version 2 Phase 2 created a controlled real historical benchmark
and opened one protected final test. Version 2 Phase 3 added walk-forward research and a
development campaign that rejected all candidates under predeclared promotion gates.

Phase 4 therefore begins without an approved shadow model. It may build operational
infrastructure that observes data readiness and would be capable of admitting a future
model, but model-connected real-data inference remains locked.

## 3. Phase 3 Handoff

The Phase 3 handoff contains three binding facts:

- Phase 3 was accepted and released as `v2.0.0-alpha.3`.
- The owner-run development campaign ended with `NO CANDIDATE PROMOTION`.
- Protected evaluation was not executed, and no candidate was admitted to shadow mode.

These facts mean Phase 4 must default to `NO APPROVED SHADOW MODEL`. The Phase 2 selected
model, the highest-ranked Phase 3 development candidate, a dummy model, or any fallback model
must not be silently substituted for a separately approved shadow model.

## 4. Entry Gates

Phase 4 has two gates.

Gate A - Infrastructure Entry is satisfied for this branch because Phase 3 is complete and
released and the owner explicitly authorized Phase 4 specification and infrastructure-first
scaffolding. Gate A permits shadow architecture, market-data readiness policy, freshness and
completeness controls, calendar and scheduling policy functions, idempotency, shadow
persistence design, monitoring, alert schemas, run-state management, proposal schemas,
model-admission locks, synthetic tests, and manual run-once scaffolding.

Gate B - Model-Connected Shadow Inference is not satisfied. It requires a separately
approved model candidate with immutable approved metadata. Until Gate B is satisfied,
real-data model inference must refuse to run, no model-generated `LONG` or `CASH` proposal
may be created from real market data, no fallback model may be substituted, and no dummy
model may be used outside synthetic tests.

## 5. Explicit Non-Goals

Phase 4 specification/scaffolding does not authorize:

- Phase 3 protected evaluation execution;
- model promotion;
- strategy threshold optimization;
- strategy candidate selection;
- production paper operation;
- live-money trading;
- new paper-order behavior;
- broker communication;
- automatic scheduling, daemon, worker, or cron integration;
- API write routes or dashboard execution controls;
- new assets, intraday bars, tick data, options, futures, crypto, or multi-asset support;
- cloud services, external model APIs, AutoML, deep learning, or new major model
  dependencies;
- package version bump or `v2.0.0-beta.1` tag creation.

## 6. Shadow-Mode Terminology

Real-Time Shadow Mode means the system operates according to the real exchange calendar and
newly completed daily market sessions. It does not mean intraday trading. SPY remains the
only symbol, `1Day` remains the only timeframe, and XNYS daily sessions remain the calendar
unit.

`observation_only_no_model` is the initial permitted mode. It may inspect local or synthetic
session readiness, compute deterministic run identities, record health state, and explain
why inference is unavailable. It must not generate model predictions, trade signals, broker
orders, or risk-approved orders.

`model_connected` is the future mode that would score an approved model. It is locked until
Gate B is separately satisfied.

## 7. Architecture

Phase 4 introduces the `spy_market_agent.shadow` package as a separate boundary from
research, execution, API, dashboard, and persistence. Initial modules define typed shadow
metadata, deterministic run identity, market-data readiness decisions, schedule decisions,
model admission, monitoring state, and run-policy decisions.

Allowed dependencies for this scaffold are existing project dependencies and project-owned
market-data calendar/checksum utilities. The shadow package must not import the paper
execution service, Alpaca TradingClient, broker adapters, approval services, or order
submission services.

## 8. Trust Boundaries

Shadow inputs are untrusted until their lineage, calendar semantics, freshness, completeness,
and model-admission status are validated. Missing or uncertain critical information is
`blocked`, not silently degraded.

Research artifacts are not runtime model approvals. A future model admission record must be
separate, immutable, auditable, and explicit. Shadow proposals are not executable orders.
Risk preview may inspect a hypothetical target in a later approved substage, but it must not
authorize or submit orders.

## 9. Market-Data Contract

The Phase 4 market-data contract remains:

- symbol exactly `SPY`;
- timeframe exactly `1Day`;
- exchange calendar exactly `XNYS`;
- market timezone `America/New_York`;
- one provider/feed lineage per snapshot;
- explicit adjustment policy, with `all` expected for primary Phase 1 lineage-derived data
  unless a later approved specification changes it;
- canonical checksum and dataset identity recorded;
- OHLCV validation enforced before shadow eligibility.

The shadow runner must not acquire data in this branch. Future real market-data shadow
ingestion may use the Phase 1 market-data credential boundary only after separate review.
Trading credentials are never required for shadow infrastructure.

## 10. Daily-Session Semantics

The signal session is the completed daily SPY session whose close is known. Features, if a
future approved model exists, may use information only through that session close.
Prediction occurs after session completion and provider finalization. Any executable entry
would remain no earlier than a later reviewed next-session path; this branch creates no
execution path.

Weekends and exchange holidays are not missing sessions. Non-XNYS dates are ineligible
shadow sessions. Incomplete current-session candles are rejected.

## 11. Freshness Policy

Freshness and completeness are independent. A dataset can be complete but stale, or fresh in
timestamp but incomplete. Both must be checked explicitly.

Freshness requires:

- target session is a valid XNYS session;
- the target session is complete at the injected `as_of` timestamp;
- provider finalization metadata says the daily bar is final;
- expected session data is present;
- no duplicate or out-of-order sessions are detected;
- OHLCV validation passed;
- data is not stale under the configured policy.

Provider finalization delay is not invented by this specification. It must be explicit
metadata or configuration supplied by a later approved ingestion design.

## 12. Completeness Policy

Completeness requires the expected daily session row and every required OHLCV field for the
shadow input snapshot. Missing expected data, duplicate sessions, out-of-order sessions,
non-finite prices, non-positive prices, negative volume, and OHLC inconsistencies are
blocking failures.

Completeness failures must produce deterministic machine-readable reasons such as
`missing_session`, `duplicate_session`, `out_of_order_sessions`, or `invalid_ohlcv`.

## 13. Exchange-Calendar Policy

The approved exchange calendar is XNYS through the project `XNYSCalendar` adapter. The
system must answer whether a target date is a valid session and whether it has completed at
a timezone-aware timestamp. Calendar uncertainty, unsupported dates, naive timestamps, or
out-of-range calendar queries fail closed.

## 14. Scheduling Policy

This branch must not create an unattended OS-level scheduler, daemon, or background worker.
It may implement deterministic policy functions that answer:

- whether today or a target date is an XNYS session;
- whether the target session is complete;
- whether provider finalization eligibility is satisfied;
- whether the logical session/configuration was already processed;
- whether the system is observation-only or model-enabled;
- whether a run is eligible;
- why a run was refused.

A later Phase 4 PR may wire these functions into explicit manual or scheduled operation
after review.

## 15. Run-Once Contract

The initial run-once contract is manual and local. It evaluates a target session, a data
snapshot lineage, a mode, and configuration metadata once. In `observation_only_no_model`
mode it may emit readiness and health state. In `model_connected` mode it must require
approved model metadata and otherwise fail before inference.

No run-once path may acquire data, construct a broker, submit an order, initialize paper
execution, or contact a trading API.

## 16. Idempotency

Each shadow run identity must be deterministic from stable inputs:

- symbol;
- signal session;
- mode;
- data snapshot lineage and canonical checksum;
- feature schema;
- model identity and checksum when applicable;
- configuration version;
- provider finalization policy identifier.

Clock time, username, hostname, absolute local paths, credentials, random UUIDs, and
unstructured operator notes must not define shadow identity. A duplicate logical run must be
detected and fail closed rather than silently creating another record.

## 17. Model-Admission Gate

Model-connected shadow mode requires immutable metadata:

- model ID;
- experiment or campaign ID;
- model artifact checksum;
- feature schema;
- label schema where relevant;
- Git/source lineage;
- approval status;
- `approved_for_shadow = true`.

The current state is `NO APPROVED SHADOW MODEL`. A model-connected request without approved
metadata must raise a typed error with machine-readable status
`blocked_no_approved_model`. Synthetic tests may use fake approved metadata to exercise the
contract; no real model is admitted by this branch.

## 18. Observation-Only Mode

`observation_only_no_model` is permitted now. It may:

- inspect local or synthetic session information;
- evaluate freshness and completeness;
- evaluate schedule eligibility;
- construct deterministic run identities;
- produce monitoring state;
- report why inference is unavailable.

It may not generate predictions, probabilities, long/cash model signals, risk-approved
orders, broker orders, or account actions. The absence of a model is an explicit state:
`blocked_no_approved_model`.

## 19. Shadow Proposal Contract

A shadow proposal is a non-executable audit object. Candidate fields include:

- `shadow_run_id`;
- `symbol`;
- `signal_session`;
- `generated_at`;
- `mode`;
- `model_id`;
- `model_checksum`;
- `feature_schema`;
- `data_lineage`;
- `predicted_probability` or `score`;
- hypothetical target state: `LONG` or `CASH`;
- admission status;
- freshness status;
- monitoring status;
- proposal status.

Observation-only mode may produce no proposal or a proposal status such as
`not_generated_observation_only`. A shadow proposal must not reuse paper-execution order
objects and must not include submit, place, cancel, replace, reconcile, liquidation, or
broker methods.

## 20. Risk-Preview Boundary

Risk preview is not execution approval. A later approved substage may allow a hypothetical
shadow target to be passed through non-mutating risk-preview checks. This branch does not
create strategy optimization, order sizing, approval, paper submission, or reconciliation.

## 21. Persistence

Phase 4 persistence must be separate from paper execution state. Initial design records may
include:

- `shadow_run`;
- `shadow_input_snapshot`;
- `shadow_health_event`;
- `shadow_proposal`;
- `shadow_alert`;
- `shadow_model_admission`.

Records must preserve immutable identities, timestamps, lineage, status transitions,
duplicate behavior, auditability, and restart/recovery semantics. Schema migrations are not
required for this first scaffold unless a later reviewed implementation needs them.

## 22. Monitoring

Required health checks include:

- market-data freshness;
- expected-session availability;
- duplicate sessions;
- invalid OHLCV;
- checksum or lineage failure;
- model admission state;
- duplicate shadow run;
- storage failure;
- configuration failure;
- clock or calendar uncertainty.

Monitoring statuses are `healthy`, `degraded`, and `blocked`. Missing or uncertain critical
information must be `blocked`.

## 23. Alerts

Initial alert events may be persisted or logged without adding external alerting
dependencies. Alert classes include:

- `stale_data`;
- `missing_session`;
- `invalid_market_data`;
- `model_not_approved`;
- `duplicate_run`;
- `persistence_failure`;
- `unexpected_configuration`;
- `lineage_failure`.

No email, SMS, Slack, cloud, or external alerting dependency is required in this scaffold.

## 24. Failure Handling

Shadow failures fail closed with deterministic reasons. Blocking examples:

- unsupported symbol, timeframe, calendar, or adjustment;
- non-XNYS target date;
- incomplete session;
- provider not finalized;
- stale data;
- missing expected session;
- duplicate or out-of-order sessions;
- invalid OHLCV;
- calendar uncertainty;
- no approved model for model-connected mode;
- duplicate shadow run;
- lineage or checksum mismatch;
- persistence failure;
- configuration failure.

Failures must not fall back to another model, another dataset, another session, another
asset, another timeframe, or a paper execution path.

## 25. Restart/Recovery Behavior

Restart and recovery must be idempotent. The same session/configuration/data snapshot/model
metadata must resolve to the same shadow run identity. If a completed or reserved run
already exists, the new attempt must fail closed or resume only through a documented recovery
state that proves the identity and prior state match. Unknown or corrupted state is
blocking.

## 26. Audit and Lineage

Every future shadow run must record:

- phase identifier `v2-phase-04`;
- package/runtime version;
- Git/source lineage;
- symbol/timeframe/calendar/timezone;
- session;
- data snapshot lineage and checksum;
- feature schema;
- model admission metadata when applicable;
- configuration version;
- freshness/completeness decision;
- schedule decision;
- monitoring status;
- proposal status when applicable.

Machine-specific local paths, usernames, hostnames, credentials, and raw provider payloads
must not define identity or appear in committed artifacts.

## 27. Security

Shadow code must not hard-code API keys, account IDs, secrets, or credentials. It must not
print secrets. It must not import or instantiate broker clients. It must not expose API write
routes, dashboard execution controls, order approval controls, or kill-switch controls.

## 28. Credential Policy

This scaffold requires no credentials. Future real market-data shadow ingestion may use
Phase 1 market-data credentials only after separate review. Trading credentials such as
paper-order keys, broker-account credentials, and live credentials are not required and must
not be read by shadow infrastructure.

## 29. CLI/API Boundaries

No Phase 4 CLI that performs real-data model inference is approved in this scaffold. No API
mutation route or dashboard execution control is approved. Future manual commands must be
explicit, local, and reviewed before they can load real market data. Importing
`spy_market_agent.shadow` must have no side effects.

## 30. Testing

Normal automated tests must be offline, synthetic, credential-free, and broker-free.
Required coverage includes:

- Phase 4 spec existence and status;
- package version remains `2.0.0a3`;
- `v2.0.0-alpha.3` documented as released;
- `v2.0.0-beta.1` documented only as a target;
- observation-only mode permitted;
- model-connected inference rejected without approval;
- synthetic approved metadata passes the admission contract;
- SPY daily XNYS policy;
- incomplete and stale sessions rejected;
- duplicate run rejected;
- deterministic run identity;
- no broker/trading imports from shadow modules;
- no automatic order submission;
- no import side effects;
- live trading remains prohibited;
- Phase 5 remains unauthorized.

## 31. Owner Testing

Owner testing for this substage should review the spec, inspect the shadow scaffold, run the
synthetic tests, and confirm no model-connected real-data shadow inference is available.
Owner testing must not rerun Phase 3 research, access protected labels, or create paper/live
orders.

## 32. Required Artifacts/Evidence

Acceptance evidence for this first Phase 4 PR should include:

- this governing specification;
- updated governance/status documentation;
- the `spy_market_agent.shadow` scaffold;
- synthetic test evidence;
- quality-gate output;
- confirmation that package version remains `2.0.0a3`;
- confirmation that no beta tag was created;
- confirmation that no model was promoted;
- confirmation that no broker/execution capability was added.

## 33. Acceptance Criteria

This substage may be accepted when:

- Phase 3 release status and `NO CANDIDATE PROMOTION` are documented accurately;
- Phase 4 Gate A and Gate B are documented;
- observation-only mode is implemented and tested;
- model-connected shadow inference is mechanically locked without approved metadata;
- deterministic shadow run identity is implemented and tested;
- freshness, completeness, and schedule policy functions fail closed;
- shadow modules have no broker/execution imports or side effects;
- normal tests remain offline and synthetic;
- coverage remains at least 85%;
- Ruff, formatting, MyPy, `git diff --check`, and `git status --short` pass;
- no real-data experiment, protected evaluation, paper order, live order, or beta tag is
  created.

## 34. Rejection Criteria

This substage must be rejected or held when:

- a model is silently promoted despite Phase 3's `NO CANDIDATE PROMOTION`;
- model-connected real-data shadow inference can run without approved metadata;
- a dummy or fallback model can run outside synthetic tests;
- shadow code imports broker clients or paper execution services;
- paper/live behavior changes;
- a scheduler, daemon, API write route, or dashboard execution control is introduced;
- intraday data, another asset, protected evaluation, strategy optimization, or live
  trading is added;
- generated real-data artifacts, credentials, account identifiers, or private paths are
  committed;
- documentation claims profitability, predictive edge, paper readiness, live readiness, or
  production readiness.

## 35. Versioning Contract

Phase 4 starts from released `v2.0.0-alpha.3` and package/runtime version `2.0.0a3`.
Specification and infrastructure-first scaffolding must not bump the package version.

The target future public release identifier is `v2.0.0-beta.1`. A later reviewed
release-preparation branch may set an appropriate beta package version after Phase 4
implementation and owner acceptance. No `v2.0.0-beta.1` tag is created by this branch.

API, database, market-data, benchmark, and research artifact schema versions do not change
merely because Phase 4 planning begins.

## 36. Approval Boundary

This specification authorizes Phase 4 infrastructure-first shadow-mode scaffolding only. It
does not authorize model-connected real-data inference, protected evaluation, strategy
optimization, production paper operation, live trading, broker communication, schedulers,
API write routes, dashboard execution controls, package version bump, or a beta tag.

Any expansion beyond this document requires explicit owner approval and a new or amended
governing specification. Model-connected shadow inference remains locked until a separate
model-admission gate approves an immutable model candidate for shadow operation.
