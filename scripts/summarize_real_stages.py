"""Summarize all six planned observations without causal attribution."""
import hashlib
import json
import statistics
import sys
from pathlib import Path


def main():
    root = Path(sys.argv[1])
    anchors = ["0bd03bf", "de1e836", "de1e836", "0bd03bf", "0bd03bf", "de1e836"]
    rows = []
    for index, anchor in enumerate(anchors):
        directory = root / f"trial-{index}-{anchor}"
        record = json.loads((directory / "result.json").read_text())
        events = [json.loads(line) for line in
                  (directory / "stages.jsonl").read_text().splitlines()]
        if not record["result_equal"] or events[-1].get("completed") is not True:
            raise ValueError(f"Trial {index} did not complete with instrument equivalence")
        entries, stages = {}, {}
        for event in events:
            if event["event"] == "enter":
                entries[event["id"]] = event
            elif event["event"] == "leave":
                entry = entries[event["id"]]
                key = entry["stage"]
                stage = stages.setdefault(key, {"calls": 0, "inclusive_wall": 0.0,
                                                 "inclusive_cpu": 0.0})
                stage["calls"] += 1
                stage["inclusive_wall"] += event["wall_seconds"]
                stage["inclusive_cpu"] += event["cpu_seconds"]
        rows.append(dict(trial=index, anchor=anchor, plain=record["plain"],
                         instrumented=record["instrumented"], stages=stages,
                         ttm_calls=record["ttm_calls"],
                         ttm_rows_sum=sum(record["ttm_input_rows"]),
                         input_sha256=record["input_sha256"],
                         harness_sha256=record["harness_sha256"],
                         environment=record["environment"],
                         result_sha256=hashlib.sha256((directory / "result.json").read_bytes())
                         .hexdigest()))
    if len({row["input_sha256"] for row in rows}) != 1:
        raise ValueError("Input database changed")
    if len({row["harness_sha256"] for row in rows}) != 1:
        raise ValueError("Harness changed")
    summary = {}
    for anchor in set(anchors):
        values = [row["plain"]["wall_seconds"] for row in rows if row["anchor"] == anchor]
        summary[anchor] = dict(median=statistics.median(values), minimum=min(values),
                               maximum=max(values), observations=values)
    differences = []
    for start in (0, 2, 4):
        pair = {row["anchor"]: row["plain"]["wall_seconds"] for row in rows[start:start+2]}
        differences.append(pair["de1e836"] - pair["0bd03bf"])
    result = dict(status="DIAGNOSTIC_ONLY", observations=rows, plain_wall_summary=summary,
                  paired_new_minus_old_seconds=differences,
                  limitation="inclusive stages overlap; no causal or historical ratio proof")
    with (root / "summary.json").open("x", encoding="utf-8", newline="\n") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    print(json.dumps({"plain_wall_summary": summary,
                      "paired_new_minus_old_seconds": differences}, indent=2))


if __name__ == "__main__":
    main()
