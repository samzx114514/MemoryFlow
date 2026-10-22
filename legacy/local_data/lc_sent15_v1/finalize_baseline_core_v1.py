from __future__ import annotations

import argparse
import importlib.util
import json
import runpy
import shutil
from pathlib import Path


def load_builder(path: Path):
    spec = importlib.util.spec_from_file_location("baseline_builder", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--builder", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    args = ap.parse_args()
    out, archive = args.output.resolve(), args.archive.resolve()
    if not out.is_dir() or archive.exists():
        raise RuntimeError("expected partial output and absent create-only archive")
    builder = load_builder(args.builder.resolve())
    shutil.copy2(args.builder.resolve(), out / "code" / args.builder.name)
    shutil.copy2(Path(__file__).resolve(), out / "code" / Path(__file__).name)
    namespace = runpy.run_path(str(out / "tests" / "test_baseline_core.py"))
    test_names = sorted(name for name in namespace if name.startswith("test_") and callable(namespace[name]))
    for name in test_names:
        if name == "test_checksums":
            continue
        namespace[name]()
    (out / "pytest_output.txt").write_text(
        f"{len(test_names)} passed (stdlib deterministic test runner)\n",
        encoding="utf-8", newline="\n",
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["tests"] = {"status": "pass", "passed": len(test_names), "output": "pytest_output.txt"}
    integrity_sha = builder.write_manifest_and_checksums(out, manifest)
    namespace["test_checksums"]()
    for expected, rel in builder.parse_checksum_file(out / "checksums.sha256"):
        if builder.sha256_file(out / rel) != expected:
            raise RuntimeError(f"final checksum failure: {rel}")
    archive_info = builder.create_archive(out, archive)
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{archive_info['sha256']}  {archive.name}\n", encoding="utf-8", newline="\n"
    )
    builder.write_json(archive.with_suffix(archive.suffix + ".report.json"), {
        "schema_version": builder.SCHEMA + "-archive-v1",
        "integrity_sha256": integrity_sha,
        "archive": archive_info,
        "scope": manifest["scope"],
        "import_policy": manifest["import_policy"],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
