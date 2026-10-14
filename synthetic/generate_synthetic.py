#!/usr/bin/env python3
"""Generate 18 synthetic UniAgent Task 2 test cases.

Replaces the earlier 16-case suite. Changes vs v1:
  + New hotel-cost cap cases (REGRESSION, SANITY, EDGE) tied to the
    E4 rule derived from VV-HRKG §8 zu Abs. 2 Nr. 2.1 (80 EUR cap
    with Messe/Grossstadt/prior-approval justification override).
  + Two more date-format variations under REGRESSION to exercise
    the resilient date parser (written German month, weekday on Ende).
  - Dropped foreign-currency, A1-cert, alcohol KNOWN_GAP cases -
    research found no authoritative source for them as rejection
    criteria at Kassel.

Categories:
    REGRESSION - patterns v4 must catch; drops here mean we broke v4.
    SANITY     - clean cases that must stay accepted.
    KNOWN_GAP  - rules that exist but we chose not to implement
                 (private-weekend extension - complex date arithmetic).
    EDGE       - boundary conditions on existing rules.
"""

import json
import shutil
from pathlib import Path


OUT = Path(__file__).parent / "synthetic_cases"


def write_case(name, files, expected, category, reason):
    """Create one case directory. Returns (truth_entry, cat_entry)."""
    case_dir = OUT / name
    case_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (case_dir / filename).write_text(content, encoding="utf-8")
    truth = {"antrag": name, "result": expected}
    cat = {"antrag": name, "category": category, "reason": reason}
    return truth, cat


# ---------- REGRESSION cases (10) ----------

def regression_cases():
    out = []

    # R1: Trip application submitted after trip start (T1)
    out.append(write_case(
        name="dienstreiseantrag-r01-late-approval",
        files={
            "antrag-dienstreise.pdf": """Dienstreiseantrag
Universitaet Kassel

Antragsteller: Dr. Max Mustermann
Fachbereich: Informatik
Datum der Antragstellung: 15.11.2026

Reiseziel: Wien, Oesterreich
Zweck: Konferenz EuroVis 2026
Start: Montag, 02.11.2026
Ende Dienstgeschaeft Wien: Freitag, 06.11.2026
""",
        },
        expected="abgelehnt",
        category="REGRESSION",
        reason="T1: Application submitted after trip start",
    ))

    # R2: Business end before trip start (T2)
    out.append(write_case(
        name="dienstreiseantrag-r02-date-contradiction",
        files={
            "antrag-dienstreise.pdf": """Dienstreiseantrag
Universitaet Kassel

Antragsteller: Prof. Dr. Anna Schmidt
Fachbereich: Maschinenbau
Datum der Antragstellung: 20.09.2026

Reiseziel: Berlin
Zweck: VDI-Jahrestagung
Start: Montag, 15.10.2026
Ende Dienstgeschaeft Berlin: 10.10.2026
""",
        },
        expected="abgelehnt",
        category="REGRESSION",
        reason="T2: Business end precedes trip start",
    ))

    # R3 NEW: Written German month format (date parser resilience)
    out.append(write_case(
        name="dienstreiseantrag-r03-written-month",
        files={
            "antrag-dienstreise.pdf": """Dienstreiseantrag
Universitaet Kassel

Antragsteller: Dr. Hans Weber
Fachbereich: Chemie
Datum der Antragstellung: 20. November 2026

Reiseziel: Hamburg
Zweck: GDCh-Vortragstagung
Start: 15. Oktober 2026
Ende Dienstgeschaeft Hamburg: 18. Oktober 2026
""",
        },
        expected="abgelehnt",
        category="REGRESSION",
        reason="T1 with written German dates (tests resilient parser)",
    ))

    # R4 NEW: Weekday prefix on Ende line (parser handles noise)
    out.append(write_case(
        name="dienstreiseantrag-r04-weekday-ende",
        files={
            "antrag-dienstreise.pdf": """Dienstreiseantrag
Universitaet Kassel

Antragsteller: Dr. Petra Lang
Fachbereich: Physik
Datum der Antragstellung: 05.09.2026

Reiseziel: Dresden
Zweck: DPG-Fruehjahrstagung
Start: Montag, 20.10.2026
Ende Dienstgeschaeft Dresden: Mittwoch, 15.10.2026
""",
        },
        expected="abgelehnt",
        category="REGRESSION",
        reason="T2 with weekday prefix on Ende line (tests resilient parser)",
    ))

    # R5: Only pro-forma invoice (E1)
    out.append(write_case(
        name="auslagenerstattung-r01-proforma-only",
        files={
            "rechnung.pdf": """PROFORMA-RECHNUNG

Lehrbuch GmbH
Universitaet Kassel - Fachbereich Informatik
Kostenstelle: 4711

Position: Fachbuch "Deep Learning Grundlagen"
Preis: 89,00 EUR inkl. MwSt.

Dies ist eine Pro-forma-Rechnung zur Anforderung.
Zahlung erst nach Erhalt der Originalrechnung.
""",
        },
        expected="abgelehnt",
        category="REGRESSION",
        reason="E1: Pro-forma invoice is not a valid receipt",
    ))

    # R6: No university affiliation (E3)
    out.append(write_case(
        name="auslagenerstattung-r02-no-university",
        files={
            "rechnung.pdf": """Rechnung Nr. R-2026-9988

Elektronik24 GmbH
Hamburger Allee 42
60486 Frankfurt am Main

Kunde: Max Privat
Privatanschrift: Bahnhofstrasse 7, 60329 Frankfurt

Position: Gaming-Tastatur RGB
Betrag: 149,00 EUR inkl. MwSt.
""",
        },
        expected="abgelehnt",
        category="REGRESSION",
        reason="E3: No reference to the university or its units",
    ))

    # R7: Real duplicate billing (L2)
    out.append(write_case(
        name="auslagenerstattung-r03-real-duplicate",
        files={
            "rechnung-vendor-01.pdf": """Rechnung Nr. R-2026-5544

TechShop GmbH
Universitaet Kassel - Fachbereich Informatik
Kostenstelle 4711

Position: USB-C Hub Model TS-HUB-200
Bestellnummer: ORDER-887766
Betrag: 59,99 EUR inkl. MwSt.
Zahlung per Karte ****0927
Rechnungsdatum: 05.10.2026
""",
            "rechnung-vendor-02.pdf": """Rechnung Nr. R-2026-5544

TechShop GmbH
Universitaet Kassel - Fachbereich Informatik
Kostenstelle 4711

Position: USB-C Hub Model TS-HUB-200
Bestellnummer: ORDER-887766
Betrag: 59,99 EUR inkl. MwSt.
Zahlung per Karte ****0927
Rechnungsdatum: 05.10.2026
""",
        },
        expected="abgelehnt",
        category="REGRESSION",
        reason="L2: Two invoices with identical order number is a real duplicate",
    ))

    # R8: Receipt + card statement for same payment (L2 payment-proof fix)
    out.append(write_case(
        name="auslagenerstattung-r04-receipt-plus-kontoauszug",
        files={
            "rechnung-konferenz.pdf": """Rechnung Nr. R-CONF-2026-091

ACM Digital Library
Universitaet Kassel - Fachbereich Informatik
Kostenstelle 4711

Position: SIGMOD 2026 Konferenzregistrierung
Rechnungsbetrag: 450,00 EUR
Zahlung erfolgt per Visa-Karte ****6031
Rechnungsdatum: 12.08.2026
""",
            "kontoauszug.pdf": """Kontoauszug - Deutsche Bank
Kontoinhaber: Dr. Lisa Mueller
IBAN: DE89 3704 0044 0532 0130 00

Buchungsdatum: 13.08.2026
Buchungstext: ACM SIGMOD 2026 KONFERENZ
Betrag: -450,00 EUR
Karte: Visa ****6031
""",
        },
        expected="angenommen",
        category="REGRESSION",
        reason="L2 fix: receipt + card statement for same payment is NOT duplicate",
    ))

    # R9 NEW: Hotel >80 EUR without justification (E4 new rule)
    out.append(write_case(
        name="auslagenerstattung-r05-hotel-over-cap",
        files={
            "rechnung-hotel.pdf": """Rechnung Nr. R-HOTEL-2026-442

Marriott Hamburg
Universitaet Kassel - Fachbereich Informatik
Kostenstelle 4711

Uebernachtung: 1 Nacht Einzelzimmer
Datum: 15.09.2026
Zimmerpreis: 185,00 EUR inkl. MwSt.

Zahlung per Firmenkarte.
""",
        },
        expected="abgelehnt",
        category="REGRESSION",
        reason="E4: Hotel >80 EUR without Messe/Grossstadt/approval justification",
    ))

    # R10: Procurement over EUR 1000 without 3 quotes (P1)
    out.append(write_case(
        name="beschaffungsantrag-r01-missing-quotes",
        files={
            "beschaffungsantrag.pdf": """Beschaffungsantrag
Universitaet Kassel - Fachbereich Mathematik

Position: Konferenzserver Dell PowerEdge R750
Summe brutto: 4.800,00 EUR

Antragsteller: Dr. Peter Weber
Datum: 01.10.2026
""",
            "angebot-dell.pdf": """Angebot Nr. A-2026-DELL-01
Dell Technologies

Fuer: Universitaet Kassel

Dell PowerEdge R750 Server
Preis: 4.800,00 EUR brutto
""",
        },
        expected="abgelehnt",
        category="REGRESSION",
        reason="P1: >1000 EUR purchase needs 3 quotes, only 1 present",
    ))

    return out


# ---------- SANITY cases (5) ----------

def sanity_cases():
    out = []

    # S1: Clean trip application
    out.append(write_case(
        name="dienstreiseantrag-s01-clean-trip",
        files={
            "antrag-dienstreise.pdf": """Dienstreiseantrag
Universitaet Kassel

Antragsteller: Dr. Thomas Richter
Fachbereich: Physik
Datum der Antragstellung: 05.09.2026

Reiseziel: Muenchen
Zweck: DPG-Jahrestagung 2026
Start: Montag, 20.10.2026
Ende Dienstgeschaeft Muenchen: Freitag, 24.10.2026
""",
        },
        expected="angenommen",
        category="SANITY",
        reason="Clean trip, submitted well before start",
    ))

    # S2: Clean expense
    out.append(write_case(
        name="auslagenerstattung-s01-clean-expense",
        files={
            "rechnung.pdf": """Rechnung Nr. R-2026-7001

Springer Fachbuch-Verlag
Universitaet Kassel - Fachbereich Mathematik
Kostenstelle 5522

Position: Lehrbuch "Algebra II"
Betrag: 65,00 EUR inkl. MwSt.
Zahlungsart: Rechnung
Rechnungsdatum: 10.09.2026
""",
        },
        expected="angenommen",
        category="SANITY",
        reason="Clean expense: real invoice, mentions university",
    ))

    # S3 NEW: Hotel >80 EUR WITH Messe justification
    out.append(write_case(
        name="auslagenerstattung-s02-hotel-messe",
        files={
            "rechnung-hotel.pdf": """Rechnung Nr. R-HOTEL-2026-887

Hotel Steigenberger Frankfurt
Universitaet Kassel - Fachbereich Informatik
Kostenstelle 4711

Uebernachtung: 2 Naechte Einzelzimmer
Datum: 12.-14.11.2026
Zimmerpreis: 180,00 EUR pro Nacht inkl. MwSt.

Anmerkung: Messe-Zuschlag wegen Buchmesse Frankfurt.
Keine Alternative verfuegbar aufgrund der Messe-Veranstaltung.
""",
        },
        expected="angenommen",
        category="SANITY",
        reason="E4 justification: hotel >80 EUR OK with Messe keyword",
    ))

    # S4 NEW: Hotel >80 EUR WITH Grossstadt justification
    out.append(write_case(
        name="auslagenerstattung-s03-hotel-grossstadt",
        files={
            "rechnung-hotel.pdf": """Rechnung Nr. R-HOTEL-2026-991

Berlin Marriott Hotel
Universitaet Kassel - Fachbereich Wirtschaft
Kostenstelle 6611

Uebernachtung: 1 Nacht Einzelzimmer
Datum: 20.11.2026
Zimmerpreis: 150,00 EUR inkl. MwSt.

Anmerkung: Grossstadt-Zuschlag Berlin.
Reiseziel liegt im Innenstadtbereich einer Grossstadt.
""",
        },
        expected="angenommen",
        category="SANITY",
        reason="E4 justification: hotel >80 EUR OK with Grossstadt keyword",
    ))

    # S5: Clean procurement under EUR 1000
    out.append(write_case(
        name="beschaffungsantrag-s01-clean-procurement",
        files={
            "beschaffungsantrag.pdf": """Beschaffungsantrag
Universitaet Kassel - Lehrstuhl fuer Chemie

Position: 10 x Erlenmeyer-Kolben 500 ml
Summe brutto: 285,00 EUR

Antragsteller: Dr. Julia Herrmann
Datum: 03.10.2026
""",
            "angebot-labware.pdf": """Angebot Nr. A-2026-LAB-99
LabWare Kassel GmbH

Fuer: Universitaet Kassel - Lehrstuhl Chemie

10 x Erlenmeyer-Kolben 500 ml Borosilikat
Preis: 285,00 EUR brutto
""",
        },
        expected="angenommen",
        category="SANITY",
        reason="Clean procurement under EUR 1000 threshold",
    ))

    return out


# ---------- KNOWN_GAP cases (1) ----------
# Research found weekend-extension IS a real HRKG rule but complex to
# implement. Keep as documented gap. Removed foreign-currency, A1-cert,
# and alcohol cases - no authoritative source as rejection criteria.

def known_gap_cases():
    out = []

    # K1: Weekend extension (private days mixed in)
    out.append(write_case(
        name="dienstreiseantrag-k01-private-weekend",
        files={
            "antrag-dienstreise.pdf": """Dienstreiseantrag
Universitaet Kassel

Antragsteller: Dr. Elena Petrova
Fachbereich: Physik
Datum der Antragstellung: 15.09.2026

Reiseziel: Rom, Italien
Zweck: Workshop Teilchenphysik
Start: Donnerstag, 22.10.2026
Ende Dienstgeschaeft Rom: Freitag, 23.10.2026
Rueckreise: Montag, 26.10.2026 (private Verlaengerung Wochenende)
""",
        },
        expected="abgelehnt",
        category="KNOWN_GAP",
        reason="Private weekend extension needs cost separation (not implemented)",
    ))

    return out


# ---------- EDGE cases (2) ----------

def edge_cases():
    out = []

    # E1: Hotel at EXACTLY 80 EUR (boundary of E4 rule)
    out.append(write_case(
        name="auslagenerstattung-e01-hotel-exactly-80",
        files={
            "rechnung-hotel.pdf": """Rechnung Nr. R-HOTEL-2026-500

Hotel Ibis Kassel
Universitaet Kassel - Fachbereich Mathematik
Kostenstelle 5522

Uebernachtung: 1 Nacht Einzelzimmer
Datum: 20.09.2026
Zimmerpreis: 80,00 EUR inkl. MwSt.
""",
        },
        expected="angenommen",
        category="EDGE",
        reason="E4 boundary: hotel at exactly 80 EUR must pass (rule is strict >80)",
    ))

    # E2: Procurement at exactly EUR 1000 (boundary of P1)
    out.append(write_case(
        name="beschaffungsantrag-e01-exactly-threshold",
        files={
            "beschaffungsantrag.pdf": """Beschaffungsantrag
Universitaet Kassel - Fachbereich Biologie

Position: Analytische Waage SM-1000
Summe brutto: 1.000,00 EUR

Antragsteller: Dr. Rainer Fuchs
Datum: 06.10.2026
""",
            "angebot-waage.pdf": """Angebot Nr. A-2026-WAAGE-01
LabScales GmbH

Fuer: Universitaet Kassel - Fachbereich Biologie

Analytische Waage SM-1000
Preis: 1.000,00 EUR brutto
""",
        },
        expected="angenommen",
        category="EDGE",
        reason="P1 boundary: strict >1000, exactly 1000.00 should pass",
    ))

    return out


# ---------- Main ----------

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    all_entries = []
    all_entries.extend(regression_cases())
    all_entries.extend(sanity_cases())
    all_entries.extend(known_gap_cases())
    all_entries.extend(edge_cases())

    truth_path = OUT / "ground-truth.jsonl"
    cat_path = OUT / "categories.jsonl"

    with truth_path.open("w", encoding="utf-8") as f:
        for truth, _ in all_entries:
            f.write(json.dumps(truth, ensure_ascii=False) + "\n")

    with cat_path.open("w", encoding="utf-8") as f:
        for _, cat in all_entries:
            f.write(json.dumps(cat, ensure_ascii=False) + "\n")

    by_cat = {}
    for _, cat_entry in all_entries:
        c = cat_entry["category"]
        by_cat[c] = by_cat.get(c, 0) + 1

    print(f"Generated {len(all_entries)} synthetic cases in {OUT}")
    for cat in ("REGRESSION", "SANITY", "KNOWN_GAP", "EDGE"):
        if cat in by_cat:
            print(f"  {cat:12s} {by_cat[cat]}")
    print(f"\nManifests:")
    print(f"  {truth_path}")
    print(f"  {cat_path}")


if __name__ == "__main__":
    main()
