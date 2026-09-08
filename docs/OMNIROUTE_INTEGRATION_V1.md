# OmniRoute Integration V1

## Purpose

Integrate OmniRoute as an optional local execution fabric while keeping Everstate as the canonical project-state and truth authority.

## Non-negotiable boundary

Everstate owns:

- project identity
- state version
- objective
- current task
- decisions and constraints
- blockers and failures
- next action
- evidence, authority, freshness, conflict status
- continuation readiness

OmniRoute may own:

- provider credentials
- provider/model discovery
- request translation
- account/model routing
- quota and cost optimization
- provider health and circuit breakers
- transport retries and fallback

OmniRoute memory and Context Relay are contextual evidence only. They must never directly mutate canonical Everstate state or upgrade a claim to VERIFIED.

## Architecture

```text
Everstate Continuation Planner
          |
          +-- Native ProviderAdapter path
          |
          +-- ExecutionFabric
                  |
                  +-- OmniRouteFabric -- HTTP /v1 --> OmniRoute
                                                  --> provider/model/account
```

The integration uses the public OpenAI-compatible `/v1` contract. Everstate does not import OmniRoute internal TypeScript modules and does not share its SQLite database.

## Environment

- `EVERSTATE_OMNIROUTE_URL` defaults to `http://127.0.0.1:20128/v1`
- `EVERSTATE_OMNIROUTE_API_KEY` optionally supplies a bearer token
- `EVERSTATE_OMNIROUTE_TIMEOUT` defaults to `3.0` seconds

Provider credentials remain in OmniRoute. Everstate stores no duplicate provider secrets.

## Phased rollout

### Phase 1 — Fabric contract

Additive only. No native behavior changes.

- `ExecutionFabric` protocol
- OmniRoute HTTP client
- `/v1/models` discovery
- health classification
- non-streaming `/v1/chat/completions`
- transport/error validation
- secret-safe config representation

Gate: full Everstate CI green.

### Phase 2 — Capability and routing bridge

- normalize OmniRoute model metadata
- expose candidate capabilities to Everstate routing
- keep semantic suitability in Everstate
- keep quota/cost/operational suitability in OmniRoute

Gate: deterministic routing tests and native-path regression tests.

### Phase 3 — Verified continuation envelope

- build minimal verified continuation context from canonical Everstate state
- never send the full Everstate database
- include state version, project identity, task, constraints, next action, and verified repository evidence
- reject or surface stale/conflicting context

Gate: packet round-trip tests plus zero cross-project leakage tests.

### Phase 4 — Live failover

- source becomes unavailable without cooperation
- Everstate performs zero-source-contact failover
- OmniRoute selects an available destination
- destination verifies repository identity and HEAD
- destination reports conflicts before work

Gate: SAFC/ZSCB live acceptance.

### Phase 5 — Work continuation

- destination performs one minimal reversible task
- relevant tests pass
- full suite remains green
- canonical Everstate state is updated only through Everstate-owned capture

Gate: Successful Cross-AI Continuation Rate acceptance.

### Phase 6 — Optional telemetry/MCP integration

Only after HTTP integration is stable:

- health/quota/cost telemetry
- optional MCP management surface
- A2A only if a concrete task-lifecycle requirement exists

## Failure invariants

1. Everstate must continue to work when OmniRoute is not installed or is down.
2. OmniRoute must never become the canonical state store.
3. No OmniRoute memory/relay content can silently override verified repository evidence.
4. Provider secrets must not be copied into Everstate state or handoff artifacts.
5. Cross-project leakage remains a release blocker.
6. Native Claude/Codex/Gemini paths remain available as a fallback during rollout.
7. No success claim is made without targeted tests and full-suite CI.

## Phase 1 acceptance checklist

- [ ] OmniRoute is optional
- [ ] no new runtime dependency required
- [ ] base URL is validated
- [ ] API key is excluded from config repr
- [ ] `/models` parsing is tested
- [ ] bearer auth is tested
- [ ] timeout behavior is tested
- [ ] transport failure maps to UNAVAILABLE
- [ ] reachable/no-model state maps to DEGRADED
- [ ] non-streaming chat request shape is tested
- [ ] malformed responses fail closed
- [ ] full Everstate CI is green
