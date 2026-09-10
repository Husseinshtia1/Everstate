# EVR-SYSTEM-001 — Real Full-System Autobuild

This benchmark is the first end-to-end acceptance run intended to let Everstate coordinate a real project build rather than only verify isolated routing or continuation contracts.

## What it tests

The run uses:

1. a clean Git workspace,
2. Everstate canonical project identity/state,
3. selectable semantic state depth,
4. configured execution fabrics for AgentCouncil participants,
5. Ruflo forced as the council orchestrator,
6. a real multi-round council debate,
7. a real primary coding-agent handoff that may modify the repository,
8. canonical-state preservation checks, and
9. deterministic project verification through `everstate acceptance-evaluate`.

The coding agent is not given a second manually rewritten explanation after state seeding. It receives the task through Everstate's continuation/handoff path.

## State levels

`minimal`
: objective + current task + next action.

`guarded`
: minimal plus decisions and active constraints.

`full`
: guarded plus a known failed attempt and current blocker. This is the release-significant mode for the first real run.

## Ubuntu preparation

From the Everstate repository:

```bash
git checkout feat/real-system-acceptance
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Install Ruflo if it is not already available:

```bash
node --version
npm install -g 'claude-flow@^3'
everstate ruflo-check
```

Configure execution fabrics interactively once:

```bash
everstate setup
```

For the first full council run, configure enough eligible model targets that this command shows at least two participants:

```bash
everstate council "preflight" --path . --dry-run --orchestrator ruflo --json
```

That particular command requires the current repository itself to be initialized in Everstate. The benchmark runner performs its own equivalent preflight inside the isolated benchmark workspace, so it is fine to skip this manual check.

Make sure the primary coding agent is installed and authenticated. First run target:

```bash
codex --version
```

## First real run

Use a fresh workspace and the full state level:

```bash
bash benchmarks/system_v1/pulseboard_autobuild/run_real.sh \
  "$HOME/everstate-live/EVR-SYSTEM-001" \
  codex \
  full
```

The run intentionally fails rather than silently downgrading if Ruflo is unavailable or fewer than two council participants are eligible.

To rerun from a clean copy at the same path:

```bash
EVERSTATE_REAL_RESET=1 \
  bash benchmarks/system_v1/pulseboard_autobuild/run_real.sh \
  "$HOME/everstate-live/EVR-SYSTEM-001" \
  codex \
  full
```

## Other primary agents

The same benchmark can be run without changing the canonical mission:

```bash
bash benchmarks/system_v1/pulseboard_autobuild/run_real.sh /tmp/evr-claude claude full
bash benchmarks/system_v1/pulseboard_autobuild/run_real.sh /tmp/evr-gemini gemini full
bash benchmarks/system_v1/pulseboard_autobuild/run_real.sh /tmp/evr-local codex-ollama full
bash benchmarks/system_v1/pulseboard_autobuild/run_real.sh /tmp/evr-omni codex-omniroute full
```

## Evidence captured

The workspace retains `.everstate/real-acceptance/` with:

- Ruflo readiness,
- council preflight/participants,
- council result,
- canonical packet before the coding run,
- canonical packet after the coding run,
- status before/after,
- primary-agent terminal output, and
- the final JSON acceptance report.

The final line is either:

```text
EVR-SYSTEM-001: PASS
```

or:

```text
EVR-SYSTEM-001: FAIL
```

A PASS means the project implementation satisfies the deterministic verifier and the seeded semantic state survived the coding-agent run. It does not by itself prove every external provider is generally reliable; the evidence records which providers/models actually participated in this run.
