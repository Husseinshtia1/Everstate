from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "extensions" / "claude-desktop"
REQUIRED_FILES = ("manifest.json", "server/proxy.js")


def validate_extension(extension_dir: Path) -> dict:
    for relative in REQUIRED_FILES:
        candidate = extension_dir / relative
        if not candidate.is_file():
            raise RuntimeError(f"missing MCPB file: {candidate}")

    manifest = json.loads((extension_dir / "manifest.json").read_text(encoding="utf-8"))
    required = ("manifest_version", "name", "version", "description", "author", "server")
    missing = [field for field in required if field not in manifest]
    if missing:
        raise RuntimeError(f"manifest is missing required fields: {', '.join(missing)}")
    if manifest["manifest_version"] != "0.3":
        raise RuntimeError(f"unsupported manifest version: {manifest['manifest_version']}")
    if manifest["server"].get("entry_point") != "server/proxy.js":
        raise RuntimeError("Everstate MCPB entry point must remain server/proxy.js")
    return manifest


def build(output: Path, extension_dir: Path = EXTENSION_DIR) -> Path:
    manifest = validate_extension(extension_dir)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    # Deterministic timestamps make local bundle hashes reproducible across builds.
    timestamp = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(REQUIRED_FILES):
            data = (extension_dir / relative).read_bytes()
            info = zipfile.ZipInfo(relative, timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)

    with zipfile.ZipFile(output, "r") as archive:
        names = set(archive.namelist())
        if names != set(REQUIRED_FILES):
            raise RuntimeError(f"unexpected MCPB contents: {sorted(names)}")
        packaged = json.loads(archive.read("manifest.json").decode("utf-8"))
        if packaged["name"] != manifest["name"] or packaged["version"] != manifest["version"]:
            raise RuntimeError("packaged manifest identity mismatch")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Everstate Claude Desktop MCPB bundle.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "everstate-capture-0.1.0.mcpb",
    )
    args = parser.parse_args()
    result = build(args.output)
    print(result)


if __name__ == "__main__":
    main()
