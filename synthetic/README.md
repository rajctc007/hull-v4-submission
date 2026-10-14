# Synthetic Test Cases for hull-v4

Based on publicly available University of Kassel policies and the
Hessian Travel Costs Act (HRKG). Four categories:

- **REGRESSION** - reworded spot-check patterns v4 must still catch,
  plus a specific regression test for the L2 payment-proof false
  positive that was fixed on 2026-10-13.
- **SANITY** - clean cases that must pass without rejection.
- **KNOWN_GAP** - cases based on policies v4 does NOT yet enforce.
  Expected result is the HRKG-correct one, so these INITIALLY FAIL -
  they document coverage gaps rather than being bugs.
- **EDGE** - boundary conditions on existing rules.

## Current cases (16)

**Dienstreise (5):**
- r01 late-approval (REGRESSION, T1)
- r02 date-contradiction (REGRESSION, T2)
- s01 clean-trip (SANITY)
- k01 no-A1-certificate (KNOWN_GAP)
- k02 private-weekend-extension (KNOWN_GAP)

**Auslagen (6):**
- r01 proforma-only (REGRESSION, E1)
- r02 no-university (REGRESSION, E3)
- r03 real-duplicate (REGRESSION, L2 real)
- r04 receipt-plus-kontoauszug (REGRESSION, L2 payment-proof fix)
- s01 clean-expense (SANITY)
- k01 hotel-over-cap (KNOWN_GAP)
- k02 foreign-currency (KNOWN_GAP)

**Beschaffung (5):**
- r01 missing-quotes (REGRESSION, P1)
- s01 clean-procurement (SANITY)
- k01 alcohol (KNOWN_GAP)
- e01 exactly-threshold (EDGE)

## Running

```bash
cd ~/hull-v4-submission/synthetic/
source ../env.sh                       # loads OPENAI_* vars
python generate_synthetic.py           # create synthetic_cases/
python test_synthetic.py               # score v4 against them
```

The test harness monkey-patches v4's PDF reader to read our plain-text
`.pdf` files. No changes to predict.py needed.

## Interpreting results

- REGRESSION + SANITY should score 100%. If not, v4 has regressed.
- KNOWN_GAP scores show how much of the real test set we might miss.
  Example: if gap cases score 20%, expect test-set accuracy to drop
  proportionally for those rule areas.
- EDGE scores document boundary behaviour. If an EDGE case changes
  outcome unexpectedly, it signals a rule semantics change.

## The R04 case (payment-proof regression)

`auslagenerstattung-r04-receipt-plus-kontoauszug` is a dedicated
regression test for the L2 duplicate_billing false positive that
rejected `auslagenerstattung-08` in the Deepseek evaluation. It
contains a conference-fee invoice and a bank statement for the same
payment - the fix (payment-proof pre-filter) must keep this
"angenommen". If this case ever regresses to "abgelehnt", the fix in
decide_expense() has been undone.
