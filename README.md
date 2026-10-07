# business-trip-hull-v4 (DAIM Hull, LLM labeler integration)

**Deterministic parts:** PDF text extraction (pypdf), German date parsing,
per-domain decide functions, EUR amount extraction, framework-exemption
heuristics. Rules: T1 (prior approval), T2 (date contradiction), E1
(pro-forma invoice), E3 (university affiliation), P1 (three-quote threshold).

**LLM parts (narrow labelers, Python combinator):** six yes/no questions
answered by the hosted LLM, each wired to a specific rejection reason -
L1 duplicate funding, L2 duplicate billing, L3 staff hospitality, L4 IT
framework item, L5 internal arithmetic mismatch, L6 cross-document price
mismatch. Rules reject deterministically; labelers only inspect cases
that passed every deterministic rule.

**Runtime model (inside TIRA):** whatever TIRA sets OPENAI_MODEL to -
development targeted openai/gpt-oss-20b via Groq.

**Development assistant:** Claude Code.

**Known limits:** labeler L6 relies on correct supplier matching across
documents; a very long case may need chunking. Logs follow the event-
logging contract and end every case with a decision event.
