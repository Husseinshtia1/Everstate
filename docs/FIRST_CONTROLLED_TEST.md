# First controlled Everstate continuity test

This is the preflight and execution sequence for the first real user-side test on Ubuntu.

## 0. Update Everstate

```bash
cd ~/Everstate
git checkout main
git pull
source .venv/bin/activate
pip install -e '.[dev]'
```

## 1. Verify the CLI and preflight command

```bash
everstate --help
everstate-doctor --help
```

Expected Everstate commands include at least:

- providers
- continue
- export
- copy
- acceptance-seed
- acceptance-evaluate

## 2. Controlled benchmark reset

```bash
rm -rf /tmp/everstate-auth-test
mkdir -p /tmp/everstate-auth-test
cp -R ~/Everstate/benchmarks/continuity_v0/auth_redirect/project/. /tmp/everstate-auth-test/
cd /tmp/everstate-auth-test
git init
git config user.email "everstate-test@example.invalid"
git config user.name "Everstate Test"
git add .
git commit -m "interrupted baseline"
```

Confirm the benchmark is broken before handoff:

```bash
python verify.py
```

Expected: failure.

## 3. Seed interrupted state

```bash
everstate acceptance-seed \
  ~/Everstate/benchmarks/continuity_v0/auth_redirect/scenario.json \
  --path /tmp/everstate-auth-test
```

Inspect what the receiving AI will get:

```bash
everstate packet /tmp/everstate-auth-test
```

## 4. Run the release preflight gate

Passive preflight sends no project state to providers:

```bash
everstate-doctor \
  --path /tmp/everstate-auth-test \
  --require-ai
```

For the controlled AI handoff test, continue only when the result is:

```text
READY_FOR_AI_TEST
```

`PORTABLE_ONLY` means Everstate state/export is healthy but no integrated AI target is currently ready. `BLOCKED` means the project/state layer itself needs attention before testing.

Optional active provider health checks:

```bash
everstate-doctor \
  --path /tmp/everstate-auth-test \
  --active \
  --require-ai
```

Cloud active checks may consume a small amount of provider usage. The local Ollama active check may run the configured local model. No project state is used in the health prompt.

Machine-readable report:

```bash
everstate-doctor \
  --path /tmp/everstate-auth-test \
  --json
```

## 5. Inspect routing before launch

Default routing:

```bash
everstate continue \
  --path /tmp/everstate-auth-test \
  --dry-run
```

Local-first routing:

```bash
everstate continue \
  --path /tmp/everstate-auth-test \
  --mode local-first \
  --dry-run
```

Do not launch if doctor and routing disagree about the selected target.

## 6. Launch the selected provider

For the first controlled receiving-side test, use a provider that doctor reports ready.

Codex cloud:

```bash
everstate continue \
  --path /tmp/everstate-auth-test \
  --target codex
```

Gemini CLI:

```bash
everstate continue \
  --path /tmp/everstate-auth-test \
  --target gemini
```

Local Codex + Ollama, only when reported READY:

```bash
everstate continue \
  --path /tmp/everstate-auth-test \
  --target codex-ollama
```

Critical test rule: do not explain the task to the receiving AI. It must orient from Everstate state and repository evidence.

## 7. Evaluate observable continuation

After the receiving AI finishes:

```bash
everstate acceptance-evaluate \
  ~/Everstate/benchmarks/continuity_v0/auth_redirect/scenario.json \
  --path /tmp/everstate-auth-test
```

Acceptance requires the observable project outcome to pass; a provider saying it understands is not sufficient.

Record manually:

1. Did the receiving AI ask what it was supposed to do?
2. How many user interventions were required?
3. Did it repeat the rejected unsafe approach?
4. Did it orient to the correct file/problem immediately?
5. Time from launch to correct continuation.

## 8. Portable invariant

At any point, verify the provider-independent escape hatch:

```bash
everstate export --path /tmp/everstate-auth-test
```

This must produce Markdown and JSON from the same canonical Everstate state version.

## What this test proves

A pass proves controlled receiving-side continuation for this scenario and provider. It does not yet prove automatic capture from an exhausted Claude Desktop session. That requires the later session-observer/rolling-capture phase.
