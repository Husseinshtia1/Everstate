from __future__ import annotations

import argparse
from pathlib import Path

from everstate.mcpb_build import build_mcpb


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Everstate Claude Desktop MCPB bundle.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "everstate-capture-0.1.1.mcpb",
    )
    args = parser.parse_args()
    result = build_mcpb(args.output)
    print(result)


if __name__ == "__main__":
    main()
