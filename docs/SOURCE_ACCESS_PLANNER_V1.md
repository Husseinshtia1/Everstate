# Source Access Planner v1

Everstate must not begin with the most invasive or brittle source-access technique.

## Access ladder

1. `OFFICIAL_SUPPORTED`
2. `AUTHORIZED_SESSION`
3. `OFFICIAL_EXPORT`
4. `LOCAL_CACHE`
5. `MANUAL_IMPORT`

The ladder is a preference order, not a claim that every higher method is actually available. Availability and capabilities must be proven independently.

## Core rule

**Proven path > new hypothesis. Capability truth > adapter label.**

A source adapter never becomes READY merely because an application is installed, a profile exists, or a cache contains related strings.

## Capability contract

Every source path reports whether it can:

- list projects
- read project metadata
- read project instructions
- list conversations
- read conversations
- list knowledge
- read knowledge

A path is continuation-ready only when it can at minimum identify the project and read its conversations sufficiently for state bootstrap.

## Approval boundary

`LOCAL_CACHE` is recovery/fallback. Everstate must never silently escalate from a failed authorized path into cache inspection. Explicit user approval is required.

## Claude Desktop current truth

The current repository has live evidence that Claude Desktop's claude.ai renderer profile/cache exists, but the local-cache experiments have not yet proven reliable Cloud Project reconstruction. Therefore local cache remains `PARTIAL`.

An existing authorized-session path must remain `UNVERIFIED` until a live probe proves exactly what it can access on the user's machine. Once proven, it outranks export/cache/manual fallback.

## Intended UX

1. Detect source environments.
2. User chooses the source environment.
3. Show access methods and their actual status/capabilities.
4. Recommend the safest proven usable path.
5. Discover actual projects from that source through the selected access path.
6. User selects the project.
7. Read only the capabilities that path actually supports.
8. Build/review canonical Everstate state.
9. Select destination and continue.
