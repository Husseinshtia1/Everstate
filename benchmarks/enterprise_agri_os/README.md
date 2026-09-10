# EVR-AGRI-ENTERPRISE-001

This is Everstate's enterprise-scale autonomous build benchmark for an Agricultural Agentic Operating System.

It is intentionally not an MVP benchmark. The plan is decomposed into 15 gated stages. Every stage:

1. activates explicit canonical Everstate task/next-action state,
2. preserves accumulated decisions and constraints,
3. requires an independent AgentCouncil review,
4. launches the verified headless coding provider,
5. runs deterministic acceptance checks,
6. feeds failures back to the provider and retries within a bounded attempt budget,
7. stops the complete build immediately if the stage cannot reach PASS.

The protected `template/MASTER_PLAN.md` defines the product contract. The protected `template/verify_enterprise.py` is the deterministic stage verifier. Neither may be edited by the coding agent to obtain a pass.

## Zero-model preflight

```bash
EVERSTATE_REAL_DRY_RUN=1 EVERSTATE_REAL_RESET=1 \
  bash benchmarks/enterprise_agri_os/run_real.sh \
  "$HOME/everstate-live/EVR-AGRI-ENTERPRISE-001" codex ruflo
```

This validates the plan, creates an isolated workspace, seeds canonical state, checks the Codex automation preflight, resolves eligible council participants, and verifies Ruflo readiness without launching council inference or the coding task.

## Real autonomous build

```bash
EVERSTATE_REAL_RESET=1 \
  bash benchmarks/enterprise_agri_os/run_real.sh \
  "$HOME/everstate-live/EVR-AGRI-ENTERPRISE-001" codex ruflo
```

Evidence is written under:

```text
.everstate/autobuild/EVR-AGRI-ENTERPRISE-001/
```

Each stage stores preflight evidence, council output, every attempt prompt, and every deterministic attempt report. `summary.json` records the final pass/fail state.

## Important boundary

The benchmark validates that Everstate can autonomously orchestrate and verify construction of the enterprise repository. External commercial providers (satellite, weather, Deere-style machinery, regulatory systems, cloud services) cannot be live-validated without credentials. The generated project is therefore required to implement provider adapters and deterministic mock/sandbox paths. Real credentials are a separate integration acceptance gate and must never be embedded into the benchmark or model context.

The benchmark must never actuate real irrigation, chemical application, purchases, payments, or farm machinery.
