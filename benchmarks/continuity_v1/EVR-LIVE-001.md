# EVR-LIVE-001 — Cascading Provider Unavailability

Status: Required acceptance scenario for M2.5

## Origin

This scenario is derived from the first live Ubuntu Everstate run in which:

1. The original Claude environment was no longer usable for continuation.
2. Everstate preserved and emitted the correct continuation packet.
3. Codex was selected as the fallback destination.
4. Codex launch/authentication failed before task execution.
5. The user still needed a next continuation path without re-explaining the task.

## Product invariant under test

> Continuity cannot depend on the availability of the fallback provider.

## Scenario

A project has an authoritative Everstate state containing:
- objective
- current task
- active decision
- active constraints
- known failed attempt
- blocker
- next action

Provider A is unavailable.
Provider B is attempted and fails to become usable.
Provider C is ready, or a local/manual target is available.

Everstate must preserve the authoritative state across the failure chain and continue without user re-explanation.

## Required flow

```text
Project state vN
  -> Provider A probe: unavailable
  -> Provider B selected/attempted
  -> Provider B launch/auth failure
  -> Everstate records routing failure separately
  -> canonical project state remains intact
  -> Provider C receives vN, unless newer repository evidence exists
  -> Provider C completes the task
  -> deterministic project verification passes
```

## Required assertions

1. No project-state field is lost after Provider A failure.
2. No project-state field is lost after Provider B failure.
3. Routing failures are not promoted to project-domain truth.
4. Provider runtime artifacts are excluded from project modified-file state.
5. Provider C receives the same authoritative objective, task, decisions, constraints, failed attempts, blockers, and next action.
6. The user provides zero task re-explanation between provider attempts.
7. Rejected/unsafe failed approaches are not repeated unless conditions changed.
8. Protected files/constraints remain intact.
9. Final verification command passes.
10. Manual export remains available throughout the chain.

## Failure cases

The scenario fails if any of the following occurs:
- user must restate the task
- a failed provider destroys or rewrites canonical state
- Everstate silently changes trust boundary against policy
- failed provider artifacts pollute project state
- Provider C misses a critical constraint
- Provider C repeats a rejected approach without changed evidence
- final project verification fails
- no continuation path is offered after integrated providers fail

## Metrics

Capture:
- Time to Correct Continuation
- number of user interventions
- number of reorientation questions from the successful destination
- number of failed provider attempts
- whether failed approach was repeated
- whether any state field changed unexpectedly across attempts
- final acceptance score

## Release significance

M2.5 cannot be considered complete until this scenario passes in a real environment using at least:
- two independent unavailable/failing destinations, and
- one successful continuation destination or local/manual continuation path.
