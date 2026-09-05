# Claude Desktop Authorized UI Probe v1

This probe verifies only whether Everstate can hand an official `claude://` deep link to the installed Claude Desktop environment using the user's current signed-in app state.

It does **not** read Cookies, tokens, IndexedDB values, Local Storage, conversations, project instructions, or project files.

## Capability boundary

A successful deep-link navigation proves only:

- Claude Desktop is installed and registered as a `claude://` scheme handler.
- The operating system can hand an official Claude deep link to the app.
- If the user confirms the Projects screen appears, UI navigation to the signed-in Projects surface works.

It does **not** prove programmatic `list_projects`, `read_project_metadata`, `read_conversations`, or any other data-reading capability.

Anthropic documents that an invalid or missing project ID falls back to the recent chats / project list, so the probe uses:

`claude://claude.ai/project/invalid`

Opening the UI always requires an explicit `--open-projects` flag.
