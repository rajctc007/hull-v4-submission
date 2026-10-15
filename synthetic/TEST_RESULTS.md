# hull-v4 Synthetic Test Suite — Results

**Last run:** 2026-10-15
**Target:** `predict.py` with E4 hotel cap rule, L2 payment-proof filter, resilient date parsing, LLM call timeout

## Summary

| Category | Score | Interpretation |
|---|---|---|
| REGRESSION | **10/10 (100%)** | All implemented rules protected |
| SANITY | **5/5 (100%)** | Clean cases correctly accepted |
| EDGE | **2/2 (100%)** | Boundary conditions correct |
| KNOWN_GAP | 0/1 (0%) | Expected — documented gap not implemented |
| **TOTAL** | **17/18 (94%)** | |

Real public spot-check (training-20260928): **21/21 (100%)** across all three domains (trip 5/5, expense 8/8, procurement 8/8). No regression from any defensive change.

## Per-case results

### REGRESSION (10/10)

| Case | Rule tested | Expected | Got |
|---|---|---|---|
| `dienstreiseantrag-r01-late-approval` | T1 prior approval | abgelehnt | ✓ abgelehnt |
| `dienstreiseantrag-r02-date-contradiction` | T2 business end before start | abgelehnt | ✓ abgelehnt |
| `dienstreiseantrag-r03-written-month` | T1 + resilient parser (written DE) | abgelehnt | ✓ abgelehnt |
| `dienstreiseantrag-r04-weekday-ende` | T2 + resilient parser (weekday prefix) | abgelehnt | ✓ abgelehnt |
| `auslagenerstattung-r01-proforma-only` | E1 pro-forma rejection | abgelehnt | ✓ abgelehnt |
| `auslagenerstattung-r02-no-university` | E3 university affiliation | abgelehnt | ✓ abgelehnt |
| `auslagenerstattung-r03-real-duplicate` | L2 real duplicate billing | abgelehnt | ✓ abgelehnt |
| `auslagenerstattung-r04-receipt-plus-kontoauszug` | L2 payment-proof filter | **angenommen** | ✓ angenommen |
| `auslagenerstattung-r05-hotel-over-cap` | E4 HRKG hotel cap | abgelehnt | ✓ abgelehnt |
| `beschaffungsantrag-r01-missing-quotes` | P1 three-quote threshold | abgelehnt | ✓ abgelehnt |

### SANITY (5/5)

| Case | Reason | Expected | Got |
|---|---|---|---|
| `dienstreiseantrag-s01-clean-trip` | Clean trip application | angenommen | ✓ angenommen |
| `auslagenerstattung-s01-clean-expense` | Clean university expense | angenommen | ✓ angenommen |
| `auslagenerstattung-s02-hotel-messe` | Hotel 180€ with Messe justification | angenommen | ✓ angenommen |
| `auslagenerstattung-s03-hotel-grossstadt` | Hotel 150€ with Grossstadt justification | angenommen | ✓ angenommen |
| `beschaffungsantrag-s01-clean-procurement` | Procurement under 1000€ | angenommen | ✓ angenommen |

### EDGE (2/2)

| Case | Boundary | Expected | Got |
|---|---|---|---|
| `auslagenerstattung-e01-hotel-exactly-80` | E4 at exactly 80€ (rule is strict >80) | angenommen | ✓ angenommen |
| `beschaffungsantrag-e01-exactly-threshold` | P1 at exactly 1000€ (rule is strict >1000) | angenommen | ✓ angenommen |

### KNOWN_GAP (0/1 — expected)

| Case | Policy | Expected | Got | Status |
|---|---|---|---|---|
| `dienstreiseantrag-k01-private-weekend` | §13 BRKG: >5 private days rejects travel | abgelehnt | ✗ angenommen | **Not implemented** |

**Why not implemented:** Weekend extension detection requires parsing trip start, business end, AND return date, then calculating private working days (weekends excluded). Complex date arithmetic with high risk of false positives on legitimately-combined trips. Documented as a research-identified gap rather than silently ignored.

## Methodology

1. **Case generation:** `generate_synthetic.py` creates case directories under `synthetic_cases/`, each with plain-text `.pdf` files simulating German admin documents.
2. **Test harness:** `test_synthetic.py` monkey-patches `predict.read_pdf_text` to read plain-text files, routes each case to the correct `decide_*` function, and compares against `ground-truth.jsonl`.
3. **Interpretation:** REGRESSION and SANITY must stay 100% or v4 has broken. KNOWN_GAP documents real but unimplemented policies. EDGE documents behaviour at rule boundaries.

## Reproducing

```bash
cd rajesh-uniagent-solver/synthetic/
source ../env.sh                   # loads OPENAI_* (Groq or vLLM)
python generate_synthetic.py       # creates synthetic_cases/
python test_synthetic.py           # scores and prints breakdown
```

The harness assumes `predict.py` lives one directory up (`V4_DIR` override possible).

## Policy sources

- **HRKG §8 Übernachtungsgeld** — [Haufe](https://www.haufe.de/id/norm/reisekostengesetz-hessen-8-uebernachtungsgeld-HI2300904_p8.html)
- **VV-HRKG §8 zu Abs. 2 Nr. 2.1 (80 EUR threshold)** — [Uni Marburg](https://www.uni-marburg.de/de/universitaet/administration/verwaltung/dezernat2/rechtsvorschriften/reisekostenuebersicht/20200327_vv_hrkg.pdf/@@download/file/20200327_vv_hrkg.pdf)
- **BRKG §13 — private day combination** — [FU Berlin merkblatt](https://www.mi.fu-berlin.de/fb/service/office_net/Dateien/Merkblatt-Verbindung-Dienstreisen-mit-privatem-Aufenthalt.pdf)

## History

| Date | Event |
|---|---|
| 2026-10-13 | Suite v1 — 16 cases including speculative KNOWN_GAP (foreign currency, A1 cert, alcohol, weekend). |
| 2026-10-15 | Suite v2 — 18 cases. Dropped unverified KNOWN_GAPs after research found no authoritative Kassel/HRKG source for them as rejection criteria. Added hotel cap tests (REGRESSION, SANITY ×2, EDGE) tied to the new E4 rule. Added date-format regression tests (written month, weekday prefix on Ende). |
