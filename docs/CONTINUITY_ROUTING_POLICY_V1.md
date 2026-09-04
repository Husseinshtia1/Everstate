# Everstate Continuity Routing Policy v1

Status: Proposed for M2.5

This document defines how Everstate chooses, explains, retries, and audits continuation destinations.

## 1. Hard gates before scoring

A target is eligible only if all required gates pass:

1. Provider/runtime discovered or explicitly configured.
2. Provider policy allows this target for the project.
3. Authentication is usable if required.
4. Provider is not in a known hard-unavailable state.
5. Required local resources exist for local targets.
6. Target can accept the continuation packet format or adapter transformation.

If a hard gate fails, the provider score is not considered.

## 2. Target state model

Each target probe returns:

- provider_id
- provider_type: cloud_agent | local_runtime | generic_api | manual
- state
- state_reason
- capabilities
- locality: local | cloud | mixed | manual
- auth_state
- executable_or_endpoint
- probe_timestamp
- policy_allowed
- details_safe_for_user

Required state values are defined in `CONTINUITY_UX_V1.md`.

## 3. Readiness probe rules

Probe actions must be minimal and side-effect free whenever possible.

Allowed examples:
- executable discovery
- version command
- local endpoint health request
- credential-presence/readiness checks that do not expose credentials
- lightweight provider status checks

Do not send project source, project state, or continuation packets during readiness probing.

## 4. Recommendation score

Initial normalized score (0-100):

- readiness confidence: 30
- task capability fit: 25
- context adequacy: 15
- repository/tool capability: 10
- privacy/policy preference: 10
- cost preference: 5
- latency preference: 5

Suggested pseudocode:

```text
if not hard_gates_pass(target):
    target.eligible = false
else:
    score = readiness*30
          + task_fit*25
          + context_fit*15
          + tool_fit*10
          + privacy_fit*10
          + cost_fit*5
          + latency_fit*5
```

The exact scoring coefficients may evolve after real-world data. The first implementation should keep them explicit and testable rather than learned or opaque.

## 5. User policy modifiers

### Auto
Use score ranking among eligible targets.

### Local First
Apply a strong preference to capable local targets, but never select a local target that fails capability or resource gates.

### Cloud Best
Prefer eligible cloud targets with strong task capability.

### Ask Me
Do not auto-select; sort targets and show them.

Per-project allow/deny policy always overrides preference mode.

## 6. Failure classification

Every continuation attempt returns one of:

- STARTED
- COMPLETED
- USER_CANCELLED
- NOT_INSTALLED
- NEEDS_LOGIN
- AUTH_EXPIRED
- LIMIT_REACHED
- RATE_LIMITED
- NETWORK_UNAVAILABLE
- PROVIDER_OUTAGE
- MODEL_UNAVAILABLE
- LOCAL_MODEL_MISSING
- LOCAL_RESOURCE_INSUFFICIENT
- POLICY_BLOCKED
- LAUNCH_FAILED
- UNKNOWN_FAILURE

A failed destination is recorded as an attempt event, not as canonical project truth unless it produces relevant evidence about the project itself.

## 7. Cascading fallback

Everstate may offer the next destination after a failed launch, but must never silently move to a different trust boundary if the user's policy requires confirmation.

Example:

```text
Attempt 1: Claude Code -> LIMIT_REACHED
Attempt 2: Codex -> AUTH_EXPIRED
Recommendation 3: Gemini CLI -> READY
Recommendation 4: LM Studio -> READY_LOCAL
Manual export -> ALWAYS_READY
```

No provider failure should require a new `acceptance-seed`, a fresh project initialization, or user re-explanation.

## 8. State immutability across routing attempts

The canonical continuation packet is generated from one state version before launch.

During a chain of failed provider launches:
- project state version remains authoritative
- provider launch artifacts do not become project modifications
- provider failures are appended to routing audit history
- a later provider gets the same authoritative state unless new repository evidence appeared

If repository evidence changes between attempts, Everstate must refresh and produce a newer state version before continuing.

## 9. Manual fallback invariant

Manual continuation must always exist unless explicitly disabled by policy.

Minimum manual outputs:
- human-readable Markdown packet
- machine-readable JSON packet

Clipboard export is optional by platform support but preferred.

Invariant:

```text
number_of_ready_integrated_targets may be 0
number_of_possible_continuation_paths must never be 0
```

## 10. Local runtime policy

Local targets must be treated as first-class providers.

Readiness must consider:
- runtime installed
- endpoint reachable
- at least one suitable model available
- memory/resource sufficiency estimate
- required tool/repository access

Everstate may recommend a model but must not automatically download or delete models without approval.

If local capability is lower than the cloud task requirement, Everstate should explain the tradeoff rather than mark local as universally equivalent.

## 11. Generic endpoint policy

The generic OpenAI-compatible adapter should support user-configured:
- base URL
- model
- authentication source
- optional capability metadata

Secrets must not be written into continuation packets or audit logs.

## 12. Audit record

Each routing attempt should eventually persist:

```text
attempt_id
project_id
state_version
target_id
started_at
finished_at
result
failure_class
user_selected_or_recommended
routing_mode
score_snapshot
policy_snapshot
```

This audit stream is distinct from project-domain state.

## 13. First implementation order

M2.5A — provider state and capability models
M2.5B — provider registry and probes
M2.5C — `everstate providers`
M2.5D — deterministic routing score
M2.5E — `everstate continue`
M2.5F — cascading launch failure handling
M2.5G — manual export/copy
M2.5H — Gemini CLI adapter
M2.5I — Ollama adapter
M2.5J — LM Studio / OpenAI-compatible adapter
M2.5K — EVR-LIVE-001 cascading-unavailability acceptance scenario

## 14. Release gate

Do not call M2.5 complete because providers can be listed or launched.

The release gate is observable continuity across a provider failure chain with:
- zero state loss
- zero silent policy violation
- no user re-explanation
- constraints preserved
- failed attempts preserved
- final task verification passing
