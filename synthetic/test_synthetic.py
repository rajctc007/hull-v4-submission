#!/usr/bin/env python3
"""Run v4 against synthetic cases, bypassing PDF reading.

Monkey-patches predict.read_pdf_text to read .pdf files as plain text
(our generator writes text content into .pdf-named files, so file
discovery via glob('*.pdf') still works). Then calls predict.decide()
on each synthetic case and scores against ground-truth.jsonl.

Usage from inside the synthetic/ folder:
    source ../env.sh                       # loads OPENAI_* vars
    python generate_synthetic.py           # create synthetic_cases/
    python test_synthetic.py               # score v4 against them

The harness assumes predict.py and llm_label.py live one directory up
from this file. Override by setting V4_DIR.
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
V4_DIR = Path(os.environ.get("V4_DIR", HERE.parent))
SYN = HERE / "synthetic_cases"

# Make v4 importable
sys.path.insert(0, str(V4_DIR))

if not os.environ.get("OPENAI_API_KEY"):
    sys.exit("ERROR: OPENAI_API_KEY not set. Run `source ../env.sh` first.")

import predict  # noqa: E402
from event_log import CaseTracer  # noqa: E402


# Monkey-patch: read .pdf files as plain text
def plain_text_read(pdf_path):
    try:
        return pdf_path.read_text(encoding="utf-8")
    except Exception:
        return ""


predict.read_pdf_text = plain_text_read


# Load ground truth and category metadata
def load_jsonl(path):
    out = {}
    for line in Path(path).open(encoding="utf-8"):
        if line.strip():
            obj = json.loads(line)
            out[obj["antrag"]] = obj
    return out


truth = load_jsonl(SYN / "ground-truth.jsonl")
cats = load_jsonl(SYN / "categories.jsonl")

results = {}
for case_dir in sorted(SYN.iterdir()):
    if not case_dir.is_dir():
        continue
    name = case_dir.name
    tracer = CaseTracer(name)
    try:
        result, begr = predict.decide(case_dir, tracer)
    except Exception as e:
        result, begr = "abgelehnt", f"[error] {e}"
    results[name] = {"result": result, "begruendung": begr}

# Score with category breakdown
by_cat = {}
total_ok = 0
print("\n" + "=" * 100)
print(f"{'STATUS':6s}  {'CASE':50s}  {'CATEGORY':12s}  WANT -> GOT")
print("=" * 100)
for name in sorted(truth):
    want = truth[name]["result"]
    got = results.get(name, {}).get("result", "MISSING")
    ok = want == got
    cat = cats.get(name, {}).get("category", "?")
    by_cat.setdefault(cat, [0, 0])
    by_cat[cat][1] += 1
    if ok:
        by_cat[cat][0] += 1
        total_ok += 1
    mark = "OK   " if ok else "WRONG"
    print(f"  {mark}  {name:50s}  {cat:12s}  {want:11s} -> {got}")

print("=" * 100)
print(f"\n{'Category':15s} Score")
print("-" * 30)
for cat, (ok, tot) in sorted(by_cat.items()):
    pct = 100 * ok // tot
    print(f"{cat:15s} {ok}/{tot} = {pct}%")
print(f"\n{'TOTAL':15s} {total_ok}/{len(truth)} = {100*total_ok//len(truth)}%")

print("\nInterpretation:")
print("  REGRESSION - must stay 100%. Drops mean we broke v4.")
print("  SANITY     - must stay 100%. False-rejects are serious.")
print("  KNOWN_GAP  - currently expected to miss. Shows test-set risk.")
print("  EDGE       - boundary conditions, documented behaviour.")
