#!/usr/bin/env python3
"""Score predictions.jsonl files against ground-truth.jsonl files.

Usage:
    python score.py --truth <file> [<file> ...] --predictions <file> [<file> ...]

Both --truth and --predictions accept multiple files, so you can merge all
three domains in one scoring call. The script also accepts shell globs,
e.g. --predictions out-*/predictions.jsonl.
"""

import argparse
import json
import sys
from pathlib import Path


def load(path: str) -> dict[str, str]:
    out = {}
    for line in Path(path).open(encoding="utf-8"):
        if not line.strip():
            continue
        obj = json.loads(line)
        out[obj["antrag"]] = obj["result"]
    return out


def domain_of(case: str) -> str:
    if case.startswith("dienstreise"):
        return "trip"
    if case.startswith("auslagen"):
        return "expense"
    if case.startswith("beschaffung"):
        return "procurement"
    return "other"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--truth", nargs="+", required=True,
                   help="One or more ground-truth.jsonl files.")
    p.add_argument("--predictions", nargs="+", required=True,
                   help="One or more predictions.jsonl files.")
    args = p.parse_args()

    truth: dict[str, str] = {}
    for t in args.truth:
        truth.update(load(t))

    pred: dict[str, str] = {}
    for f in args.predictions:
        pred.update(load(f))

    if not truth:
        print("No truth loaded — check --truth paths.", file=sys.stderr)
        sys.exit(1)

    by = {"trip": [0, 0], "expense": [0, 0], "procurement": [0, 0]}
    total = 0
    for case in sorted(truth):
        want = truth[case]
        got = pred.get(case, "-- MISSING --")
        ok = want == got
        d = domain_of(case)
        by[d][1] += 1
        if ok:
            by[d][0] += 1
            total += 1
        mark = "OK   " if ok else "WRONG"
        print(f"  {mark} {case:30s} got={got:12s} want={want}")

    print()
    for name, (c, t) in by.items():
        if t:
            print(f"  {name:12s} {c}/{t} = {100 * c // t}%")
    pct = 100 * total // len(truth)
    print(f"  {'TOTAL':12s} {total}/{len(truth)} = {pct}%")
    print(f"  always-reject baseline is 11/21 = 52%")


if __name__ == "__main__":
    main()
