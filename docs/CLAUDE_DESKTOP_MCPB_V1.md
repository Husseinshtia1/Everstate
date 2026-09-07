# Claude Desktop MCPB Capture v1

## Purpose

Everstate must capture structured project state while work is still possible so a later usage limit or provider outage does not require cooperation from the unavailable provider.

This integration uses Claude Desktop's supported MCP Bundle / desktop-extension mechanism. The extension is intentionally thin: it launches the locally installed `everstate-mcp` runtime and forwards MCP stdio. Everstate remains the sole owner of canonical state.

## Security boundary

Each installed/configured extension instance requires:

1. an explicit `everstate-mcp` executable path;
2. exactly one explicit project root.

The extension passes that root as `EVERSTATE_ALLOWED_ROOT`. The MCP server performs an exact resolved-path check before every capture/status operation. A call targeting another project is rejected before project registration or state mutation.

The Node proxy:

- requires absolute executable and project paths;
- verifies both exist;
- launches the executable directly with `shell: false`;
- has no network code;
- has no cookie/token/cache/Claude-internal access;
- forwards only MCP stdio and stderr.

## Data captured

The current v1 capture tool accepts one structured item at a time:

- objective
- task
- decision
- constraint
- failure
- blocker
- next_action

Raw full conversation transcripts and secrets are explicitly outside the default capture contract.

## Build

From the Everstate repository:

```bash
python scripts/build_everstate_mcpb.py
```

Default output:

```text
dist/everstate-capture-0.1.0.mcpb
```

The packager validates the required manifest identity and emits a minimal deterministic MCPB ZIP containing only:

```text
manifest.json
server/proxy.js
```

You may also validate/package with the upstream `mcpb` CLI if installed.

## Install in Claude Desktop

Claude Desktop currently supports custom local MCP bundles through:

```text
Settings → Extensions → Advanced settings → Extension Developer → Install Extension…
```

Select the generated `.mcpb` file.

Configure:

- Everstate MCP executable: the absolute `everstate-mcp` path, e.g. `/home/life/Everstate/.venv/bin/everstate-mcp` on the current development host.
- Project root: exactly one project directory for this test.

## Acceptance gate

The live test must prove all of the following before we call the Claude capture path ready:

1. Claude Desktop shows the Everstate extension connected.
2. `everstate_capture` is visible as a tool.
3. A capture for the configured project updates the expected canonical Everstate state.
4. A capture request for another project is rejected and does not register or mutate that project.
5. After Claude becomes unavailable, `everstate-emergency-failover` builds a bundle with `source_contacted=false`.
6. The destination continuation packet contains the latest captured state and no marker from another project.

## Non-claims

A successful MCPB install does not by itself prove continuous automatic capture. The AI/client still decides when to invoke MCP tools unless a stronger host lifecycle hook is available. We therefore test actual tool invocation and resulting canonical state before treating capture coverage as proven.
