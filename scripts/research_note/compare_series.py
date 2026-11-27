"""Bit-for-bit comparison of two run_vintage_series.py outputs.

Volatile fields (generated_at, stage_seconds) are listed but not compared.
Every other field is compared through its JSON text with sorted keys; Python
writes floats as the shortest repr that round-trips, so equal text means equal
float bits (NaN and -0.0 included). Exit code 1 if any field differs.
"""

import json
import sys

VOLATILE = {"generated_at", "stage_seconds"}


def text(v):
    return json.dumps(v, sort_keys=True)


old, new = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:3])
differs = 0
for key in sorted(set(old) | set(new)):
    if key in VOLATILE:
        print(f"  skip     {key} (volatile)")
        continue
    if key == "series":
        for name in sorted(set(old[key]) | set(new[key])):
            a, b = old[key].get(name), new[key].get(name)
            same = a is not None and b is not None and text(a) == text(b)
            n = len(a["ic"]) if a else 0
            print(f"  {'SAME' if same else 'DIFFERS':8s} series.{name} ({n} per-date IC values)")
            differs += not same
        continue
    same = key in old and key in new and text(old[key]) == text(new[key])
    print(f"  {'SAME' if same else 'DIFFERS':8s} {key}")
    differs += not same
print(f"\n{differs} field(s) differ" if differs else "\nALL COMPARED FIELDS IDENTICAL")
sys.exit(1 if differs else 0)
