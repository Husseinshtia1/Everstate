# EVR-SYSTEM-001 — Pulseboard Autobuild

Build a small but production-shaped local CLI named **Pulseboard**.

## Product contract

Create `pulseboard.py` in this project root using Python 3.11+ and the standard library only.

The CLI must accept a database path before the subcommand:

```bash
python pulseboard.py --db ./pulseboard.json add "Ship release" --priority high
python pulseboard.py --db ./pulseboard.json list --json
python pulseboard.py --db ./pulseboard.json done 1
python pulseboard.py --db ./pulseboard.json stats
```

### `add TITLE --priority {low,normal,high}`

- Default priority is `normal`.
- Persist a new task with a positive integer `id`.
- IDs are monotonically increasing and are never reused.
- New tasks have status `open`.
- Print the created task as one JSON object to stdout.

Task JSON shape:

```json
{"id": 1, "title": "Ship release", "priority": "high", "status": "open"}
```

### `list [--status {open,done}] --json`

- With `--json`, print a JSON array of tasks sorted by ascending `id`.
- `--status` filters the result.
- Without `--json`, a readable text representation is acceptable.

### `done ID`

- Mark the task as `done` and persist it.
- Print the updated task as one JSON object.
- Unknown IDs must exit with code `2` and a useful message on stderr.

### `stats`

Print one JSON object with exactly these top-level keys:

```json
{
  "total": 3,
  "open": 2,
  "done": 1,
  "by_priority": {"low": 0, "normal": 1, "high": 2}
}
```

All priority keys must always be present, including zero counts.

## Persistence requirements

- Store data in the path supplied by `--db`.
- Use JSON, not SQLite.
- The database must contain enough metadata to preserve monotonic IDs after tasks are completed.
- Writes must be atomic: write a temporary file in the same directory and replace the target with `os.replace` (or an equivalent standard-library atomic replace).
- Create parent directories for the database path when needed.
- A missing database starts empty.

## Safety and scope

- Standard library only. Do not install or import third-party packages.
- No network access or network libraries.
- Do not modify `SPEC.md`.
- Do not modify `verify.py`.
- Do not hard-code verifier outputs; the verifier creates fresh temporary databases and exercises multiple state transitions.
- Keep all application behavior inside this project directory.

## Documentation

Create `README.md` containing concise usage examples for all four commands and a note that Pulseboard is local-only and uses JSON persistence.

## Completion condition

The project is complete only when:

```bash
python verify.py
```

exits with code `0`.
