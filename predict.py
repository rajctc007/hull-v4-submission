#!/usr/bin/env python3
"""UniAgent Task 2 reviewer - v4 (deterministic rules + LLM labelers).

Architecture (TRAC-inspired: LLM as labeler, Python as judge):
  * decide_trip / decide_expense / decide_procurement handle each domain.
  * Each decide function first applies deterministic rules (fast, free,
    always same answer). If no deterministic rule fires, it falls through
    to narrow LLM labeler calls that check cross-document semantic
    conditions. The LLM never makes the final decision alone - a Python
    `if` ties the labeler's boolean answer to a specific rejection reason.
  * Every LLM call is logged to the event trace per the UniAgent contract.
  * One case fails -> that case gets a conservative REJECT and the batch
    continues; a crash in one case must never stop the whole run.

Environment variables (required for the LLM path):
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
"""

import argparse
import json
import os
import re
import sys
import traceback
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from llm_label import ask_boolean
from event_log import CaseTracer, LogWriter

ACCEPTED = "angenommen"
REJECTED = "abgelehnt"

# Context limit for LLM calls. Spot-check cases go up to ~5000 chars; keep
# some headroom for the test set without blowing token budgets.
LLM_CONTEXT_LIMIT = 10000

GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "maerz": 3, "marz": 3, "märz": 3,
    "april": 4, "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}

GERMAN_MONTHS_SHORT = {
    "jan": 1, "feb": 2, "mar": 3, "mär": 3, "mrz": 3, "apr": 4,
    "mai": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "okt": 10, "nov": 11, "dez": 12,
}

ENGLISH_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# ------------------------------- helpers --------------------------------------


def read_pdf_text(pdf_path: Path) -> str:
    try:
        reader = PdfReader(pdf_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def read_all_case_text(case_dir: Path) -> str:
    """Concatenate text of every PDF with a file-name header so the LLM can
    tell which document a quote came from."""
    chunks = []
    for pdf in sorted(case_dir.glob("*.pdf")):
        chunks.append(f"=== FILE: {pdf.name} ===\n" + read_pdf_text(pdf))
    return "\n\n".join(chunks)


def find_file_startswith(case_dir: Path, prefix: str) -> Path | None:
    for pdf in sorted(case_dir.glob("*.pdf")):
        if pdf.name.lower().startswith(prefix):
            return pdf
    return None


def parse_german_date(raw: str) -> date | None:
    raw = raw.strip()
    numeric = re.match(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", raw)
    if numeric:
        d, m, y = (int(x) for x in numeric.groups())
        try:
            return date(y, m, d)
        except ValueError:
            return None
    written = re.match(r"(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]+)\s*(\d{4})", raw)
    if written:
        d = int(written.group(1))
        m = GERMAN_MONTHS.get(written.group(2).lower())
        y = int(written.group(3))
        if m:
            try:
                return date(y, m, d)
            except ValueError:
                return None
    return None


def extract_date_field(text: str, pattern: str) -> date | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return parse_german_date(match.group(1)) if match else None


def extract_amounts_eur(text: str) -> list[float]:
    amounts = []
    for m in re.finditer(r"([\d]{1,3}(?:\.\d{3})*,\d{2})\s*(?:€|EUR)", text):
        raw = m.group(1).replace(".", "").replace(",", ".")
        try:
            amounts.append(float(raw))
        except ValueError:
            pass
    return amounts

def _month_from_name(name: str) -> int | None:
    """Look up a month number from any German or English name/abbreviation."""
    name = name.lower().rstrip(".")
    return (
        GERMAN_MONTHS.get(name)
        or GERMAN_MONTHS_SHORT.get(name)
        or ENGLISH_MONTHS.get(name)
    )


def _normalise_year(y: int) -> int:
    """Convert a 2-digit year to 4-digit (assuming 20xx)."""
    return y + 2000 if y < 100 else y


def find_date_near_label(text: str, label_pattern: str) -> date | None:
    """Find the first date within ~150 chars after a label match.

    Robust to realistic variations in German admin paperwork:
      - Numeric DE:  15.10.2026  /  15.10.26  /  15. 10. 2026
      - Written DE:  15. Oktober 2026  /  15. Okt. 26  /  15. Mrz 2026
      - English:     22 Oct 2026  /  22nd Oct 26  /  October 22, 2026
      - Weekday prefix ("Montag, ...") is tolerated for all forms.
    """
    label_match = re.search(label_pattern, text, flags=re.IGNORECASE)
    if not label_match:
        return None

    window = text[label_match.end():label_match.end() + 60]

    # Strip ordinal suffixes attached to digits so "22nd" -> "22".
    window = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", window, flags=re.IGNORECASE)

    # Try numeric (dd.mm.yy or dd.mm.yyyy) first.
    numeric = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{2,4})\b", window)
    if numeric:
        d, m, y = (int(x) for x in numeric.groups())
        try:
            return date(_normalise_year(y), m, d)
        except ValueError:
            pass

    # Try German-style "dd. Month yyyy" (short or full).
    de_written = re.search(
        r"(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]{3,})\.?\s*(\d{2,4})\b",
        window,
    )
    if de_written:
        d = int(de_written.group(1))
        m = _month_from_name(de_written.group(2))
        y = int(de_written.group(3))
        if m:
            try:
                return date(_normalise_year(y), m, d)
            except ValueError:
                pass

    # Try English "dd Month yyyy".
    en_dmy = re.search(
        r"(\d{1,2})\s+([A-Za-z]{3,})\.?\s+(\d{2,4})\b", window
    )
    if en_dmy:
        d = int(en_dmy.group(1))
        m = _month_from_name(en_dmy.group(2))
        y = int(en_dmy.group(3))
        if m:
            try:
                return date(_normalise_year(y), m, d)
            except ValueError:
                pass

    # Try English "Month dd, yyyy".
    en_mdy = re.search(
        r"([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{2,4})\b", window
    )
    if en_mdy:
        m = _month_from_name(en_mdy.group(1))
        d = int(en_mdy.group(2))
        y = int(en_mdy.group(3))
        if m:
            try:
                return date(_normalise_year(y), m, d)
            except ValueError:
                pass

    return None

def llm_check(tracer: CaseTracer, question: str, context: str, rule_id: str):
    """Call the labeler, log it as a model_call event, return the result."""
    r = ask_boolean(question, context[:LLM_CONTEXT_LIMIT])
    tracer.log(
        "model_call",
        model=os.environ.get("OPENAI_MODEL", "-"),
        tool=None,
        input={
            "rule_id": rule_id,
            "question": question,
            "context_length": len(context),
        },
        output={
            "answer": r.answer,
            "evidence": r.evidence,
            "tokens": {"total": r.tokens},
            "cited_sources": [],
        },
    )
    return r


# ----------------------------- business trip ----------------------------------


def decide_trip(case_dir: Path, tracer: CaseTracer) -> tuple[str, str]:
    tracer.log("input", input={"case": case_dir.name, "type": "business_trip"})

    form = find_file_startswith(case_dir, "antrag")
    tracer.log("tool_call", tool="find_application_form",
               input={"prefix": "antrag"},
               output={"path": form.name if form else None})
    if form is None:
        return REJECTED, "No application form (antrag-*.pdf) found."

    text = read_pdf_text(form)
    tracer.log("tool_call", tool="read_pdf", input={"file": form.name},
               output={"text_length": len(text)})
    if not text:
        return REJECTED, "Application form is unreadable."

    submitted = find_date_near_label(text, r"Datum\s+der\s+Antragstellung:")
    trip_start = find_date_near_label(text, r"Start:")
    business_end = find_date_near_label(text, r"Ende\s+Dienstgesch\w*(?:\s+\w+)?:")

    # Rule T1 - prior approval
    if submitted and trip_start and submitted > trip_start:
        tracer.log("observation", output={"rule": "T1_prior_approval", "fired": True})
        return REJECTED, (
            f"Application submitted on {submitted.strftime('%d.%m.%Y')} "
            f"after trip started on {trip_start.strftime('%d.%m.%Y')} "
            "- prior approval missing."
        )

    # Rule T2 - internal contradiction
    if business_end and trip_start and business_end < trip_start:
        tracer.log("observation", output={"rule": "T2_internal_contradiction", "fired": True})
        return REJECTED, (
            f"Form is inconsistent: business end "
            f"{business_end.strftime('%d.%m.%Y')} precedes trip start "
            f"{trip_start.strftime('%d.%m.%Y')}."
        )

    # Labeler L1 - duplicate funding (scholarship covers same costs)
    all_text = read_all_case_text(case_dir)
    r = llm_check(tracer, (
        "Is there any attached letter (scholarship, grant, award, bursary, "
        "or sponsorship confirmation) that states it already covers travel "
        "costs, accommodation, or conference registration fees that this "
        "application is also claiming from the university budget?"
    ), all_text, rule_id="L1_duplicate_funding")
    if r.answer:
        tracer.log("observation", output={"rule": "L1_duplicate_funding", "fired": True})
        return REJECTED, f"Duplicate funding detected: {r.evidence}"

    return ACCEPTED, "Deterministic rules passed and no duplicate funding found."


# ------------------------------- expense --------------------------------------

UNIVERSITY_KEYWORDS = re.compile(
    r"universit[äa]t|lehrstuhl|fachbereich|fachgebiet|institut"
    r"|kostenstelle|labor|werkstatt|dienstlich",
    flags=re.IGNORECASE,
)
PROFORMA_PATTERN = re.compile(r"pro[\s-]?forma[\s-]?rechnung", flags=re.IGNORECASE)

# Payment proof documents (bank/card statements, payment receipts).
# These are NORMAL evidence that an invoice has been paid, NOT duplicate
# billing. Their presence tells us we are looking at (invoice + payment
# proof), so L2 duplicate_billing must be skipped.
PAYMENT_PROOF_PATTERN = re.compile(
    r"kontoauszug|kartenabrechnung|kreditkartenabrechnung"
    r"|zahlungs[-_\s]?(bestaetigung|beleg|nachweis)",
    flags=re.IGNORECASE,
)


def decide_expense(case_dir: Path, tracer: CaseTracer) -> tuple[str, str]:
    tracer.log("input", input={"case": case_dir.name, "type": "expense"})

    text = read_all_case_text(case_dir)
    tracer.log("tool_call", tool="read_all_pdfs", input={"dir": case_dir.name},
               output={"text_length": len(text)})
    if not text:
        return REJECTED, "No readable documents in the case directory."

    # Rule E1 - pro-forma invoice is not a valid receipt
    first_1500 = text[:1500]
    if PROFORMA_PATTERN.search(first_1500) and "RECHNUNG" in first_1500.upper():
        if not re.search(r"rechnung\s+nr\.?\s*[a-z]", text, flags=re.IGNORECASE):
            tracer.log("observation", output={"rule": "E1_proforma", "fired": True})
            return REJECTED, (
                "Only a pro-forma document was submitted; receipt rule "
                "requires an original invoice."
            )

    # Rule E3 - no university affiliation anywhere
    if not UNIVERSITY_KEYWORDS.search(text):
        tracer.log("observation", output={"rule": "E3_no_university", "fired": True})
        return REJECTED, (
            "Neither invoice nor supporting documents refer to the "
            "university or one of its units."
        )

    # Labeler L2 - duplicate billing (same order billed twice)
    # Pre-filter for L2: if the case contains a bank or card statement,
    # we are looking at an invoice plus its own payment proof. That is
    # normal expense documentation, NOT duplicate billing. Skip L2 so
    # it does not misfire on (rechnung + kontoauszug) pairs.
    pdfs = list(case_dir.glob("*.pdf"))
    has_payment_proof = any(
        PAYMENT_PROOF_PATTERN.search(p.name) for p in pdfs
    )

    if has_payment_proof:
        tracer.log("observation", output={
            "rule": "L2_duplicate_billing",
            "fired": False,
            "skipped_reason": "payment_proof_present",
        })
    else:
        # Labeler L2 - duplicate billing (same order billed twice)
        r = llm_check(tracer, (
            "Do the submitted invoices appear to be billing the SAME underlying "
            "order twice? Look for duplication signals such as identical "
            "amounts, identical item lists, identical order numbers, or "
            "identical payment references appearing on multiple invoices."
        ), text, rule_id="L2_duplicate_billing")
        if r.answer:
            tracer.log("observation", output={"rule": "L2_duplicate_billing", "fired": True})
            return REJECTED, f"Duplicate billing detected: {r.evidence}"
        
    # Rule E4 - HRKG hotel cost cap (VV-HRKG §8 zu Abs. 2 Nr. 2.1).
    # Overnight costs up to 80 EUR are automatically considered 
    # "unvermeidbar". Above 80 EUR requires justification: trade fair
    # (Messe), metropolitan area (Grossstadt / Grossstadt-Zuschlag), 
    # prior approval, or unforeseeable circumstances.
    if re.search(r"\b(?:übernachtung|uebernachtung|hotel|zimmer)\b", text, flags=re.IGNORECASE):
        hotel_amounts = extract_amounts_eur(text)
        if hotel_amounts:
            max_hotel = max(hotel_amounts)
            if max_hotel > 80:
                has_justification = re.search(
                    r"messe|großstadt|grossstadt|genehmigt|dienstreisestelle"
                    r"|unvermeidbar|außergewöhnlich|ausergewoehnlich",
                    text, flags=re.IGNORECASE,
                )
                if not has_justification:
                    tracer.log("observation", output={
                        "rule": "E4_hotel_cost_cap",
                        "fired": True,
                        "max_amount": max_hotel,
                    })
                    return REJECTED, (
                        f"Hotel cost {max_hotel:.2f} EUR exceeds HRKG VV §8 "
                        f"80 EUR threshold without justification "
                        f"(Messe, Grossstadt, prior approval)."
                    )  
    # Labeler L3 - internal staff hospitality
    r = llm_check(tracer, (
        "Does this receipt consist primarily of items for an in-house staff "
        "coffee or tea kitchen (such as coffee, tea, a kettle, mugs, or "
        "similar refreshments for university staff only, with no external "
        "guests mentioned)?"
    ), text, rule_id="L3_staff_hospitality")
    if r.answer:
        tracer.log("observation", output={"rule": "L3_staff_hospitality", "fired": True})
        return REJECTED, f"Internal staff hospitality is not reimbursable: {r.evidence}"

    return ACCEPTED, "Deterministic rules and LLM checks all passed."


# ----------------------------- procurement ------------------------------------

FRAMEWORK_EXEMPTION_HINT = re.compile(
    r"wps[\s-]?(katalog|warenkorb)"
    r"|rahmenvertragspartner"
    r"|rahmenvertrag\s+(it|hardware|arbeitsplatzger)",
    flags=re.IGNORECASE,
)


def decide_procurement(case_dir: Path, tracer: CaseTracer) -> tuple[str, str]:
    tracer.log("input", input={"case": case_dir.name, "type": "procurement"})

    text = read_all_case_text(case_dir)
    tracer.log("tool_call", tool="read_all_pdfs", input={"dir": case_dir.name},
               output={"text_length": len(text)})
    if not text:
        return REJECTED, "No readable documents in the case directory."

    quote_files = list(case_dir.glob("angebot*.pdf"))
    has_warenkorb = any(
        "warenkorb" in p.name.lower() for p in case_dir.glob("*.pdf")
    )
    has_framework_exemption = (
        bool(FRAMEWORK_EXEMPTION_HINT.search(text)) or has_warenkorb
    )
    amounts = extract_amounts_eur(text)
    max_amount = max(amounts) if amounts else 0.0

    # Rule P1 - three quotes required above EUR 1000
    if max_amount > 1000 and len(quote_files) < 3 and not has_framework_exemption:
        tracer.log("observation", output={"rule": "P1_quote_count", "fired": True})
        return REJECTED, (
            f"Procurement over EUR 1000 (max {max_amount:.2f}) requires at "
            f"least three written quotes; only {len(quote_files)} present."
        )

    # Labeler L4 - IT framework item ordered outside framework contract
    r = llm_check(tracer, (
        "Does this procurement request include at least one item that is "
        "standard IT workplace equipment typically covered by a framework "
        "contract: specifically a desktop computer, laptop, notebook, "
        "monitor, or screen?"
    ), text, rule_id="L4_framework_item")
    if r.answer and not has_warenkorb:
        tracer.log("observation", output={"rule": "L4_framework_item", "fired": True})
        return REJECTED, (
            f"IT framework item detected without a framework ordering "
            f"(warenkorb) document: {r.evidence}"
        )

    # Labeler L5 - internal arithmetic mismatch on main form
    r = llm_check(tracer, (
        "On the main application form (Beschaffungsantrag), compare the "
        "stated 'Summe netto' (total net amount) against the sum of the "
        "listed line items (Positionen). Does the stated total MATERIALLY "
        "disagree with the sum of its own line items (more than ~5% off)? "
        "Only mark true if there is a clear numerical contradiction."
    ), text, rule_id="L5_internal_arithmetic")
    if r.answer:
        tracer.log("observation", output={"rule": "L5_internal_arithmetic", "fired": True})
        return REJECTED, f"Internal arithmetic mismatch: {r.evidence}"

    # Labeler L6 - cross-document price mismatch (Angebot vs Vergabevermerk)
    r = llm_check(tracer, (
        "This procurement case has multiple supplier offer documents "
        "(Angebot). The Vergabevermerk (procurement memo) also cites "
        "amounts from several suppliers. Do the following in order:\n"
        "  1. List every supplier that has an Angebot document, with the "
        "amount stated IN that Angebot document.\n"
        "  2. For each of those same suppliers, find the amount cited in "
        "the Vergabevermerk.\n"
        "  3. For ANY supplier, is there a material discrepancy (more than "
        "~5% different) between the amount in that supplier's own Angebot "
        "and the amount cited for them in the Vergabevermerk?\n"
        "Return true if ANY supplier shows such a discrepancy."
    ), text, rule_id="L6_cross_doc_mismatch")
    if r.answer:
        tracer.log("observation", output={"rule": "L6_cross_doc_mismatch", "fired": True})
        return REJECTED, f"Cross-document price mismatch: {r.evidence}"

    return ACCEPTED, "Deterministic rules and LLM checks all passed."


# ------------------------------- routing --------------------------------------


def decide(case_dir: Path, tracer: CaseTracer) -> tuple[str, str]:
    name = case_dir.name.lower()
    if name.startswith("dienstreise"):
        return decide_trip(case_dir, tracer)
    if name.startswith("auslagen"):
        return decide_expense(case_dir, tracer)
    if name.startswith("beschaffung"):
        return decide_procurement(case_dir, tracer)
    return REJECTED, f"Unknown case type: {case_dir.name}"


# ------------------------------- main -----------------------------------------


def input_cases(input_directory: Path) -> list[str]:
    if not input_directory.is_dir():
        raise ValueError(f"Input directory does not exist: {input_directory}")
    cases = sorted(
        path.name
        for path in input_directory.iterdir()
        if path.is_dir()
        and not path.name.startswith("retrieval-corpora")
        and any(file.is_file() for file in path.iterdir())
    )
    if not cases:
        raise ValueError(f"No application directories found in {input_directory}")
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UniAgent Task 2 reviewer v4 (rules + LLM labelers)."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    predictions = args.output / "predictions.jsonl"
    log_writer = LogWriter(args.output)

    try:
        with predictions.open("w", encoding="utf-8") as fp:
            for case in input_cases(args.input):
                tracer = CaseTracer(case)
                try:
                    result, begruendung = decide(args.input / case, tracer)
                except Exception as exc:
                    tracer.log("error", status="error", error=str(exc))
                    print(f"ERROR in {case}: {exc}", file=sys.stderr)
                    traceback.print_exc()
                    result = REJECTED
                    begruendung = f"Error during decision: {exc}"

                # Contract: every case trace must end with a decision event.
                tracer.log("decision", output={
                    "result": result,
                    "begruendung": begruendung,
                    "answer": result,
                    "cited_sources": [],
                })
                log_writer.write_tracer(tracer)

                fp.write(json.dumps(
                    {"antrag": case, "result": result, "begruendung": begruendung},
                    ensure_ascii=False,
                ) + "\n")
    finally:
        log_writer.close()


if __name__ == "__main__":
    main()
