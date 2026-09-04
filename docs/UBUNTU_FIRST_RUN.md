# Ubuntu First Run

This is the shortest path to the first Everstate continuity test on an Ubuntu machine.

## 1. Clone and install Everstate

```bash
git clone https://github.com/Husseinshtia1/Everstate.git
cd Everstate
bash scripts/bootstrap_ubuntu.sh
source .venv/bin/activate
everstate --help
```

Everstate runs locally and does not require an Everstate cloud account for this test.

## 2. Install Codex CLI

The official OpenAI install command is:

```bash
npm i -g @openai/codex
codex --version
```

If `npm` is missing, install a current Node.js/npm distribution first using your preferred Ubuntu method.

Then start Codex once and complete its normal sign-in flow:

```bash
codex
```

## 3. Important note about the current Claude state

If Claude has already hit its usage limit, do not ask Claude for a final summary. That is exactly the interruption Everstate is designed to survive.

For the first controlled acceptance run, `acceptance-seed` creates a deterministic interrupted-project state. This validates the receiving side (Everstate -> Codex) without requiring Claude to respond again.

A later run should capture a live Claude Code session before interruption to validate the complete Claude Code -> Everstate -> Codex path.

Claude Desktop and Claude Code are different integration surfaces. The current automatic provider adapter targets the `claude` CLI (Claude Code), not the desktop GUI.

## 4. Prepare the first benchmark

From the Everstate repository:

```bash
source .venv/bin/activate
rm -rf /tmp/everstate-auth-test
mkdir -p /tmp/everstate-auth-test
cp -R benchmarks/continuity_v0/auth_redirect/project/. /tmp/everstate-auth-test/
cd /tmp/everstate-auth-test
git init
git config user.email "everstate-test@example.invalid"
git config user.name "Everstate Test"
git add .
git commit -m "interrupted baseline"
```

Seed Everstate with the interrupted task state:

```bash
everstate acceptance-seed \
  --scenario /path/to/Everstate/benchmarks/continuity_v0/auth_redirect/scenario.json \
  --path /tmp/everstate-auth-test
```

Inspect what the next agent will receive:

```bash
everstate resume /tmp/everstate-auth-test
everstate packet /tmp/everstate-auth-test
```

## 5. Confirm the baseline fails

```bash
cd /tmp/everstate-auth-test
python verify.py
```

This should fail before the receiving agent fixes the task. A passing baseline means the scenario was not prepared correctly.

## 6. Hand off to Codex

```bash
everstate switch codex --path /tmp/everstate-auth-test
```

Everstate writes a version-pinned handoff packet under `.everstate/handoffs/` before launching Codex.

Do not manually explain the task to Codex. The purpose of the test is to see whether the Everstate continuation packet is sufficient.

## 7. Evaluate the result

After Codex finishes:

```bash
everstate acceptance-evaluate \
  --scenario /path/to/Everstate/benchmarks/continuity_v0/auth_redirect/scenario.json \
  --path /tmp/everstate-auth-test
```

The evaluator checks observable project outcomes, including:

- the required implementation file changed;
- protected files were not modified;
- forbidden/rejected solution patterns were not introduced;
- the scenario verification command passes.

## 8. Record the human metrics

For this first run also record:

- start time of the handoff;
- time of Codex's first correct action;
- number of clarification questions from Codex;
- number of times you had to correct Codex;
- whether Codex repeated the known rejected approach.

Do not improve the packet during the run. If it fails, preserve the failure as evidence and fix Everstate afterward.
