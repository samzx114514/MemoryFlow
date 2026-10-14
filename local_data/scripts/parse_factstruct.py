from __future__ import annotations

import argparse
import json
from pathlib import Path

from memoryflow.factstruct_parser import parse_factstruct_files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = sorted(
        path for path in args.source_root.rglob("*.log")
        if "__MACOSX" not in path.parts and "FactStruct" in path.parts and not path.name.startswith("._")
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for run in parse_factstruct_files(files):
            handle.write(json.dumps(run.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()

