# Everstate

**Keep working when your AI stops. Keep your project state yours.**

Everstate is an open-source, local-first **AI project continuity and execution control plane**. It maintains an evidence-backed canonical state for a project, moves that state between AI tools, routes execution across local/free/cloud fabrics, and coordinates multiple independent AI agents without making any individual model the owner of the project.

## Product thesis

AI tools remember fragments of the past. Everstate focuses on what is true **now**.

```text
activity -> evidence -> state transitions -> current project state -> continuation context
```

The project is separated from the AI worker:

```text
Project
  -> Everstate truth / identity / constraints
      -> replaceable AI workers
      -> execution fabrics
      -> multi-agent councils
```

## Principles

- Local-first and provider-neutral
- State > chat history
- Evidence > confident prose
- Current > merely similar
- Project identity != AI identity
- Constraints are enforced as execution policy
- Advisory agents never become canonical state authority
- Uncertainty and disagreements stay visible
- No raw source-code upload is required for local-only execution
- No account is required for the community/local runtime

## Quick start

Python 3.11+ is supported. The CI matrix validates Ubuntu, macOS, and Windows on Python 3.11, 3.12, and 3.13.

```bash
git clone https://github.com/Husseinshtia1/Everstate.git
cd Everstate
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
everstate --help
```

On Ubuntu you can also use:

```bash
bash scripts/bootstrap_ubuntu.sh
source .venv/bin/activate
```

## Project truth and continuity

Everstate keeps a versioned SQLite-backed project state with objective, current task, decisions, constraints, failed attempts, blockers, modified files, unresolved conflicts, and the expected next action.

```bash
everstate init .
everstate set-objective "Ship the authentication migration safely"
everstate set-task "Fix OAuth callback regression"
everstate decide "Provider B remains active"
everstate constraint "Do not modify database schema"
everstate fail "Provider A fallback duplicated callback handling"
everstate block "Redirect URI test is failing"
everstate next "Run the failing callback test in isolation"
everstate status
everstate resume
everstate packet
```

`everstate resume` is human-facing. `everstate packet` emits a version-pinned AI-to-AI continuation contract. Project identity survives process restart and real directory relocation while duplicate live copies are prevented from silently hijacking the original identity.

State writes are transactional, tolerate ordinary SQLite contention, preserve concurrent agent decisions, and can recover to the newest valid snapshot when a newer state record is corrupt without deleting forensic evidence.

## Execution fabrics

Everstate currently supports three execution roles:

```text
Ypipe        -> LOCAL_SOVEREIGN
FreeLLMAPI   -> FREE_REMOTE
OmniRoute    -> REMOTE_MULTI_PROVIDER
```

Configure them once:

```bash
everstate setup
```

Then use automatic execution:

```bash
everstate start "Implement the next verified task"
```

`auto` prefers local execution and safely falls through eligible fabrics when a provider becomes unavailable during execution. `cloud-preferred` reverses that preference. Canonical constraints such as `NO_CLOUD`, `LOCAL_ONLY`, `AIRGAPPED`, and `DATA_MUST_NOT_LEAVE_DEVICE` remove remote fabrics from the plan rather than treating privacy as a prompt suggestion.

## Multi-agent AgentCouncil

Everstate can ask several independent agents/models to review or debate the same project decision while retaining one canonical project state.

```bash
everstate council "Should we change the persistence architecture?"

everstate council \
  "Debate whether this migration is safe" \
  --mode debate \
  --rounds 3
```

Council participants are selected from eligible Ypipe, FreeLLMAPI, and OmniRoute targets with diversity-first selection. Responses must echo the same Everstate `project_id` and `state_version`. Minority failures can be excluded through quorum, duplicate voting is blocked, evidence coverage is reported separately from model confidence, and results become stale if canonical state advances during the discussion.

## Ruflo swarm orchestration

[Ruflo / claude-flow](https://github.com/ruvnet/ruflo) v3 is the preferred external swarm coordinator for AgentCouncil. Everstate still owns canonical truth, identity, constraints, provider routing, provider credentials, model execution, and result verification.

Ruflo requires Node.js 20+ and `claude-flow` v3:

```bash
npm install -g 'claude-flow@^3'
everstate ruflo-check
```

With Ruflo available, the normal command automatically uses it:

```bash
everstate council "Review this architecture" --orchestrator auto
```

You can force or bypass it explicitly:

```bash
everstate council "Review this architecture" --orchestrator ruflo
everstate council "Review this architecture" --orchestrator native
```

Current mapping:

```text
parallel-review
  Everstate model fan-out + Ruflo star/analysis coordination

debate
  Everstate multi-round debate + Ruflo mesh/balanced coordination
```

Ruflo does **not** receive Everstate provider credentials. Its subprocess environment is filtered. In local-only/air-gapped council modes, Everstate does not pass the human question or canonical continuation packet into Ruflo task metadata. If Ruflo is unavailable or its orchestration step fails in `auto` mode, Everstate falls back to the native council coordinator. Forced `ruflo` mode fails explicitly instead of pretending the swarm ran.

`everstate setup` reports Ruflo readiness alongside the execution fabrics.

## Validation

The repository contains deterministic acceptance coverage for real workflow failures including:

- interruption and cross-agent continuation
- partial provider outages and runtime failover
- identity drift and stale responses
- local-only / air-gapped execution enforcement
- multi-agent quorum, disagreement, abstention, and evidence coverage
- process restart and directory relocation
- duplicate live workspace identity protection
- concurrent state writers and SQLite contention
- corrupt newest state snapshots and recovery
- Git history rewrites and dirty working trees
- Windows configuration-file ACL hardening

The standard CI runs the full test suite on nine OS/Python combinations: Ubuntu, macOS, and Windows across Python 3.11/3.12/3.13. A separate live integration lane installs the current Ruflo v3 package on Node 20 and exercises real Ruflo readiness, swarm initialization, agent spawning, and task orchestration for review and debate modes.

These tests verify Everstate's orchestration contracts and the live Ruflo CLI integration. They do **not** by themselves prove every external Ypipe/FreeLLMAPI/OmniRoute service is live on every user's machine; those services still require environment-specific acceptance runs.

## Architecture boundary

```text
Everstate
├── Canonical State / Evidence / Identity
├── Privacy & Sovereignty Policy
├── Continuation
├── Execution Router
│   ├── Ypipe
│   ├── FreeLLMAPI
│   └── OmniRoute
└── AgentCouncil
    ├── Ruflo orchestration (preferred when available)
    └── Native coordination fallback
```

The key rule is simple:

**Everstate decides what is true and what is allowed. Ruflo coordinates how advisory agents collaborate.**

## Licensing

Everstate uses an open-source copyleft core with a separate commercial licensing path planned for proprietary embedding/OEM use. See repository licensing files for the current terms.
