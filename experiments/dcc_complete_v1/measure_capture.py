"""Measure capture overhead on identical requests with no concurrent GPU job."""
import json
import statistics
import time
from pathlib import Path
from urllib.request import Request, urlopen

from pipeline import URL, send, write


def plain(payload, folder):
    start = time.time()
    request = Request(URL, json.dumps({**payload, "model": "mf-model", "return_token_ids": True}).encode(),
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=900) as response:
        result = json.load(response)
    write(folder / "request.json", payload)
    write(folder / "response.json", result)
    write(folder / "timing.json", {"start": start, "end": time.time()})


def measure(run, output):
    job = json.loads((run / "inputs.json").read_text())[0]
    payload = {"prompt": job["prompt_ids"], "max_tokens": 256, "temperature": 0, "seed": 0}
    output.mkdir()
    plain(payload, output / "warm_plain")
    send(payload, output / "warm_capture")
    for trial in range(3):
        order = ("plain", "capture") if trial % 2 == 0 else ("capture", "plain")
        for mode in order:
            folder = output / f"{trial}_{mode}"
            (plain if mode == "plain" else send)(payload, folder)
    rows = []
    for trial in range(3):
        row = {"trial": trial}
        for mode in ("plain", "capture"):
            folder = output / f"{trial}_{mode}"
            timing = json.loads((folder / "timing.json").read_text())
            response = json.loads((folder / "response.json").read_text())
            row[mode+"_seconds"] = timing["end"]-timing["start"]
            row[mode+"_output_tokens"] = len(response["choices"][0]["token_ids"])
        row["extra_seconds"] = row["capture_seconds"]-row["plain_seconds"]
        rows.append(row)
    write(output / "summary.json", {"rows": rows, "median_extra_seconds": statistics.median(r["extra_seconds"] for r in rows),
                                    "median_plain_seconds": statistics.median(r["plain_seconds"] for r in rows),
                                    "median_capture_seconds": statistics.median(r["capture_seconds"] for r in rows),
                                    "note": "Includes Q/K flush and local artifact copy; warm-up excluded; inspect output token counts"})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    measure(args.run, args.output)
