#!/usr/bin/env python3
"""Append-only event trace per the UniAgent event-logging contract.

Writes `run-trace.jsonl.log.gz` with one JSON object per line. Each event
carries: case_id, event_id, parent_event_id, timestamp, event_type, model,
tool, input, output, status, error. Causal chain via parent_event_id; the
last event of every case must be type `decision`.
"""

import gzip
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

VALID_EVENT_TYPES = {"input", "model_call", "tool_call", "observation",
                     "decision", "error"}


class CaseTracer:
    """Collect events for one case; LogWriter flushes them at the end."""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.events = []
        self._last_id = None

    def log(self, event_type, *, model="-", tool=None,
            input=None, output=None, status="ok", error=None, parent=None):
        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"invalid event_type: {event_type}")
        event_id = "evt-" + uuid.uuid4().hex[:12]
        self.events.append({
            "case_id": self.case_id,
            "event_id": event_id,
            "parent_event_id": parent if parent is not None else self._last_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "model": model,
            "tool": tool,
            "input": input,
            "output": output,
            "status": status,
            "error": error,
        })
        self._last_id = event_id
        return event_id


class LogWriter:
    """Streams case traces to run-trace.jsonl.log.gz."""

    def __init__(self, output_dir):
        self.path = Path(output_dir) / "run-trace.jsonl.log.gz"
        self._fp = gzip.open(self.path, "wt", encoding="utf-8")

    def write_tracer(self, tracer: CaseTracer):
        for ev in tracer.events:
            self._fp.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def close(self):
        self._fp.close()
