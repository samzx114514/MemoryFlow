"""Full-call matrix persistence and trace selection for provenance_v2."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .full_replay import FixedHeadReplay, select_gpu
from .model import text_sha


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, payload):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(temp, path)


def select_calls(run: Path, user_id: str | None):
    rows = [json.loads(line) for line in (run / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    predictions = run / "predictions.jsonl"
    if user_id is None and predictions.is_file():
        completed = {row["user_id"] for line in predictions.read_text(encoding="utf-8").splitlines() if line.strip()
                     for row in [json.loads(line)] if row.get("status") == "completed" and row.get("user_id")}
        if len(completed) == 1:
            user_id = completed.pop()
    users = {row.get("user_id") for row in rows}
    if user_id is None and len(users) > 1:
        raise ValueError("Multiple recorded episodes; provide --user-id")
    chosen = [(index, row) for index, row in enumerate(rows) if user_id is None or row.get("user_id") == user_id]
    if not chosen:
        raise ValueError("No calls in the selected episode")
    return chosen, user_id


def replay_run(args):
    import numpy as np

    run, out = args.run.resolve(), args.out.resolve()
    chosen, user_id = select_calls(run, args.user_id)
    out.mkdir(parents=True, exist_ok=True)
    source_hash = digest(run / "calls.jsonl")
    model = args.model_dir.resolve()
    checkpoint = {name: digest(model / name) for name in ("config.json", "tokenizer.json", "tokenizer_config.json")}
    checkpoint["weights"] = {path.name: [path.stat().st_size, path.stat().st_mtime_ns]
                             for path in sorted(model.glob("*.safetensors"))}
    identity = {"calls_sha256": source_hash, "user_id": user_id,
                "layer": args.layer, "head": args.head, "checkpoint": checkpoint}
    identity_path = out / "replay_identity.json"
    if identity_path.exists():
        if json.loads(identity_path.read_text(encoding="utf-8")) != identity:
            raise ValueError("Replay identity differs; choose a new output directory")
    else:
        write_json(identity_path, identity)

    select_gpu(args.gpu)
    engine = None
    entries = {}
    for index, row in chosen:
        call_id = f"call{index:02d}"
        metadata_path = out / f"{call_id}.json"
        scores_path = out / f"{call_id}.npy"
        generations = (row.get("response") or {}).get("generations") or []
        request = row.get("request") or {}
        if len(generations) != 1 or not request.get("messages"):
            raise ValueError(f"{call_id} lacks a single recorded request/response")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else None
        if metadata is None or not scores_path.is_file() or metadata["scores_sha256"] != digest(scores_path):
            if engine is None:
                engine = FixedHeadReplay(model, args.layer, args.head, args.memory_cap_gib)
            started = time.monotonic()
            metadata, scores = engine.run(request, generations[0])
            temp = scores_path.with_suffix(".npy.tmp")
            with temp.open("wb") as stream:
                np.save(stream, scores, allow_pickle=False)
            os.replace(temp, scores_path)
            metadata.update(call_id=call_id, scores_sha256=digest(scores_path), seconds=time.monotonic() - started,
                            input_sha256=text_sha(json.dumps(request, ensure_ascii=False, sort_keys=True)),
                            output_sha256=text_sha(metadata["output"]))
            write_json(metadata_path, metadata)
        entries[call_id] = {"metadata": metadata_path.name, "metadata_sha256": digest(metadata_path),
                            "scores": scores_path.name, "scores_sha256": metadata["scores_sha256"],
                            "rows": metadata["output_tokens"], "columns": len(metadata["columns"]),
                            "prompt_tokens": metadata["prompt_tokens"]}
        print(json.dumps({"call_id": call_id, "rows": entries[call_id]["rows"],
                          "columns": entries[call_id]["columns"], "seconds": round(metadata["seconds"], 3)}), flush=True)
    write_json(out / "manifest.json", {"schema": "memoryflow.full_replay.v1", **identity, "calls": entries})
    return entries
