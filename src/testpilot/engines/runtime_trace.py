from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TraceEvent:
    kind: str
    name: str
    status: str = "observed"
    timestamp: str = ""
    source: str = "workflow_runner"
    data: dict[str, Any] | None = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat(timespec="milliseconds")
        if self.data is None:
            self.data = {}

    def to_dict(self):
        return asdict(self)


class TraceCollector:
    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or uuid.uuid4().hex
        self.events: list[TraceEvent] = []

    def record(self, kind: str, name: str, status: str = "observed", source: str = "workflow_runner", **data):
        event = TraceEvent(kind, name, status, source=source, data=data)
        self.events.append(event)
        return event

    def start_span(self, name: str, **data):
        return self.record("span.start", name, data=data)

    def finish_span(self, name: str, status: str = "passed", **data):
        return self.record("span.finish", name, status=status, data=data)

    def to_dict(self):
        return {"trace_id": self.trace_id, "events": [event.to_dict() for event in self.events]}
