#!/usr/bin/env python3
"""LLM labeler for narrow, factual propositions.

Design (TRAC-inspired): the LLM only extracts atomic facts (true/false
with evidence). All decision logic stays in predict.py. This separation
keeps the final decision deterministic and auditable, and keeps token
usage low.

Environment variables (same as the TIRA baseline uses):
    OPENAI_API_KEY     - API key for the hosted LLM
    OPENAI_BASE_URL    - endpoint, e.g. https://api.groq.com/openai/v1
    OPENAI_MODEL       - model name, e.g. openai/gpt-oss-20b
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


MAX_RETRIES = 2
MAX_TOKENS = 500
TEMPERATURE = 0


@dataclass
class LabelResult:
    """One LLM labeler call's outcome, kept simple so it serialises for logging."""
    answer: bool
    evidence: str
    raw: str
    tokens: int
    reasoning: Optional[str] = None


def _client() -> OpenAI:
    return OpenAI(
        base_url=os.environ["OPENAI_BASE_URL"],
        api_key=os.environ["OPENAI_API_KEY"],
    )


def _parse_json(text: str) -> Optional[dict]:
    """Extract the first JSON object with an 'answer' key from arbitrary text."""
    if not text:
        return None
    # Models sometimes wrap JSON in ``` fences or add prose; grep braces.
    candidates = re.findall(
        r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, flags=re.DOTALL
    )
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "answer" in obj:
            return obj
    return None


def ask_boolean(
    question: str,
    context: str,
    *,
    model: Optional[str] = None,
    reasoning_effort: str = "low",
) -> LabelResult:
    """Ask a yes/no question about the given context and parse the answer.

    The model is instructed to return JSON of the form:
        {"answer": true|false, "evidence": "<short quote or reason>"}

    Retries up to MAX_RETRIES times on malformed output. If every attempt
    fails to parse, returns a conservative LabelResult(answer=False, ...)
    with the raw text preserved as evidence so the caller can see why.
    """
    client = _client()
    chosen_model = model or os.environ.get("OPENAI_MODEL", "openai/gpt-oss-20b")

    system = (
        "You are a careful compliance checker. Answer in strict JSON only:\n"
        '  {"answer": true, "evidence": "<short quote or paraphrase>"}\n'
        '  {"answer": false, "evidence": "<reason or quote>"}\n'
        "The answer must be a boolean. Do not add any text outside the JSON."
    )
    user = f"Documents:\n{context}\n\nQuestion: {question}"

    raw = ""
    tokens = 0
    reasoning = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                reasoning_effort=reasoning_effort,
            )
        except TypeError:
            # Older openai clients may not accept reasoning_effort directly.
            response = client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                extra_body={"reasoning_effort": reasoning_effort},
            )

        msg = response.choices[0].message
        raw = msg.content or ""
        tokens = response.usage.total_tokens
        reasoning = getattr(msg, "reasoning", None)

        parsed = _parse_json(raw)
        if parsed is not None and isinstance(parsed.get("answer"), bool):
            return LabelResult(
                answer=parsed["answer"],
                evidence=str(parsed.get("evidence", "")).strip()[:500],
                raw=raw,
                tokens=tokens,
                reasoning=reasoning,
            )

        # Nudge the model on retry.
        user += "\n\nReminder: respond with JSON only. No prose, no code fences."

    # All retries failed to produce a parseable boolean. Return conservative
    # false so the deterministic layer stays in control.
    return LabelResult(
        answer=False,
        evidence=f"[parse-failed] {raw[:300]}",
        raw=raw,
        tokens=tokens,
        reasoning=reasoning,
    )


if __name__ == "__main__":
    # Minimal self-check: ask a trivially true question.
    r = ask_boolean(
        question="Does the document mention water?",
        context="Water is a liquid that makes things wet.",
    )
    print(f"answer:   {r.answer}")
    print(f"evidence: {r.evidence!r}")
    print(f"tokens:   {r.tokens}")
