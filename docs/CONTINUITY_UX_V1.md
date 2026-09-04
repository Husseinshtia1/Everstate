# Everstate Continuity UX Specification v1

Status: Proposed for M2.5

## Product promise

When the current AI can no longer continue, Everstate gives the user the safest available way to keep working without rebuilding project context.

Primary user action:

```bash
everstate continue
```

North-star UX principle:

> One action gives you the safest available way to keep working.

Everstate must never silently trade correctness, privacy, security, or user intent for convenience.

## Core UX model

Everstate separates two concerns:

1. Preserve verified project state.
2. Route that state to the best available continuation target.

The user should not need to think in terms of adapters, APIs, tokens, or model backends during normal use.

### Default flow

```text
Current AI stops
  -> Everstate confirms project state is safe
  -> Everstate probes continuation targets
  -> Everstate recommends the best ready target
  -> User presses Enter to continue
  -> If launch fails, Everstate preserves state and offers the next target
  -> Manual export remains available at all times
```

## Continuity targets v1

### Native cloud agents
- Claude Code
- OpenAI Codex
- Gemini CLI

### Local targets
- Ollama
- LM Studio

### Generic target
- OpenAI-compatible endpoint

### Universal fallback
- Copy continuation packet to clipboard
- Export Markdown packet
- Export JSON packet

Manual export is a first-class target, not an error path.

## Routing modes

Everstate supports four user-selectable routing policies.

### Auto
Recommend the highest-scoring ready target and make it the default Enter action.

### Local First
Prefer a capable local target before cloud providers.

### Cloud Best
Prefer the strongest available cloud target allowed by policy.

### Ask Me
Always show ready targets before launching.

Auto is the default for the community CLI, but the recommendation must remain visible before launch.

## Primary CLI experience

### `everstate continue`

Example:

```text
Everstate Continuity

Project state safe — v142 captured 3s ago

Recommended
  Gemini CLI          READY
  Good fit for this coding task

[Enter] Continue
[L] Continue locally
[C] Choose another AI
[E] Export project state
[D] Details
```

The default action is a recommendation, not an invisible automatic choice.

### `everstate providers`

Shows all discovered targets and human-readable states.

```text
Claude Code    LIMIT_REACHED
Codex          AUTH_EXPIRED
Gemini CLI     READY
LM Studio      READY_LOCAL
Ollama         NOT_INSTALLED
Manual export  ALWAYS_READY
```

### `everstate continue --choose`

Shows all viable destinations and lets the user explicitly select one.

### `everstate export`

Produces a portable continuation bundle:

```text
EVERSTATE.md
everstate-state.json
```

### `everstate copy`

Copies the canonical continuation packet to the clipboard when supported.

## Human-readable provider states

Internal provider state must be richer than available/unavailable.

Required v1 states:

- READY
- READY_LOCAL
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
- UNKNOWN_FAILURE
- ALWAYS_READY

Human-facing messages must explain the next action instead of exposing stack traces by default.

Example:

```text
Codex
Needs sign-in before it can continue.

Claude Code
Unavailable — usage limit reached.

LM Studio
Ready — runs locally on this computer.
```

## Failure chaining

Provider failure must not force the user to rebuild or reseed state.

Example:

```text
Claude Code -> LIMIT_REACHED
Codex       -> AUTH_EXPIRED
Gemini CLI  -> READY
```

Everstate records each routing attempt and continues from the same canonical state.

After a failed launch:

```text
Codex couldn't continue.
Your project state is still safe.

Next available: Gemini CLI
[Enter] Continue
```

A failed destination must never destroy, rewrite, or downgrade canonical project state.

## Local fallback UX

The local path is presented as a continuity benefit, not backend configuration.

Preferred language:

```text
Cloud AI is unavailable.
Keep working locally?
```

Not:

```text
Select Ollama backend.
```

Everstate may inspect local CPU, RAM, GPU/VRAM, disk space, installed runtimes, and model availability to determine whether local continuation is viable.

Everstate must not automatically download large models or install runtimes without explicit user approval.

Discovery is automatic. Installation is explicit.

## Setup UX

First-run discovery:

```text
Everstate found:
✓ Claude Code
✓ Codex
✗ Gemini CLI
✗ Local AI

Set up fallback options now? [Recommended]
```

If an integration is absent:

```text
Gemini CLI is not installed.
It can provide another cloud fallback.

[Install]
[Show command]
[Skip]
```

Everstate must not execute package-manager or model-download actions without user approval.

## Continuity Ladder

Each project may define a preferred target order.

Example default:

```text
1. Claude Code
2. Codex
3. Gemini CLI
4. Local AI
5. Manual export
```

Examples of policy-specific ladders:

Privacy-focused:

```text
1. Local AI
2. Approved cloud provider
3. Manual export
```

Enterprise:

```text
1. Approved corporate endpoint
2. Local approved model
3. Manual export
```

The ladder influences recommendation order but must never override provider readiness, explicit project policy, or user choice.

## Recommendation transparency

Default UI stays simple. Advanced users can ask why a target was selected.

Example details:

```text
Why Gemini CLI?
✓ authenticated
✓ ready now
✓ repository/tool access
✓ suitable for coding task
✓ context requirement appears sufficient
✗ cloud execution
```

Recommendation logic must be inspectable and deterministic enough to explain.

## Routing score inputs

Initial scoring dimensions:

- Availability/readiness
- Task capability fit
- Context capacity
- Tool/repository capability
- Privacy/local preference
- User/project policy
- Cost preference
- Latency preference

Readiness and policy are hard gates. A high score cannot override a blocked or unavailable target.

## Portable continuity

Everstate must support continuation outside integrated providers.

Portable state must work for:
- browser chat products
- another computer
- another account
- a remote server
- a future provider Everstate does not yet know
- a human collaborator

The provider is replaceable. The project state is not.

## Cross-machine direction

M2.5 does not require cloud sync, but exported state must be machine-portable.

Future encrypted sync can add convenience without changing the canonical state model.

## Security and privacy requirements

- Local mode remains accountless and serverless.
- Never upload project state merely to probe provider readiness.
- Never send a packet to a provider until the user has chosen/accepted that destination.
- Respect per-project provider allow/deny policy.
- Do not expose secrets in continuation packets.
- Do not auto-install software or models without approval.
- Never silently fall back from local/private policy to cloud.

## Acceptance requirements for M2.5

A routing handoff passes only when observable project outcomes prove continuation was correct.

Required multi-provider failure scenario:

```text
Provider A unavailable
  -> state preserved
Provider B launch/auth fails
  -> state preserved
Provider C receives same authoritative state
  -> constraints survive
  -> failed attempts survive
  -> task completes
  -> project verification passes
```

Pass conditions:
- no user re-explanation required
- no canonical-state loss across failed destinations
- no repeated rejected approach unless conditions changed
- protected constraints preserved
- final verification passes
- routing attempt history is auditable
- manual export remains available throughout

## Non-goals for M2.5

Do not build yet:
- cloud sync
- team accounts
- billing
- web dashboard
- browser extension
- automatic model downloads
- large plugin marketplace
- Kubernetes or microservices

The goal is reliable continuation routing, not platform breadth.
