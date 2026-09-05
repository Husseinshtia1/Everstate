# Everstate Try Mode v1

`everstate-try` is the safest way to evaluate Everstate with one project before any provider launch or real continuation.

## Guarantees

- exactly one project per test
- uses the latest stored canonical Everstate state without refreshing it
- does not launch Claude, Codex, Gemini, Ollama, or any other provider
- does not write into the project repository
- does not mutate the canonical state version
- writes the test artifact under `~/.everstate/test-transfers/` by default

## Output bundle

Each test creates an isolated directory containing:

- `transfer-review.json` — source, source session if any, destination, project identity, state version, and test-only flags
- `continuation.md` — human/AI readable continuation packet
- `continuation.json` — machine-readable continuation packet

The metadata explicitly records:

```json
{
  "mode": "TEST_ONLY",
  "canonical_state_mutated": false,
  "provider_launched": false
}
```

## Interactive use

```bash
everstate-try
```

It reuses the same source/project/session/destination selection rules as the transfer wizard, but refuses bulk/multi-project testing.

## Explicit use

```bash
everstate-try \
  --from codex \
  --project proj_example \
  --to gemini
```

For a verified discovered session:

```bash
everstate-try \
  --from codex \
  --session <session-id> \
  --to gemini
```

If a session association is AMBIGUOUS or UNKNOWN, an explicit project is required before a test bundle can be created.

## Why one project only

The purpose of Try Mode is to prove identity, state fidelity, and portability with minimal blast radius. Bulk transfer belongs to the later execution layer after single-project continuation is empirically validated.
