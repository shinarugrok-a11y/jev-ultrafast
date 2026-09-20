"""OTel-style trace annotation without requiring an OpenTelemetry runtime."""

import time
import uuid


class Span(dict):
    def __init__(self, name, *, attributes=None, parent_id=None, trace_id=None):
        super().__init__(
            name=name,
            span_id=str(uuid.uuid4()),
            trace_id=trace_id or str(uuid.uuid4()),
            parent_id=parent_id,
            start_time=time.time(),
            end_time=None,
            attributes=dict(attributes or {}),
            events=[],
            status="ok",
        )

    def event(self, name, **attributes):
        self["events"].append({"name": name, "time": time.time(), "attributes": attributes})

    def close(self, status="ok"):
        self["end_time"] = time.time()
        self["status"] = status
        return self


class Trace:
    def __init__(self, name="jev.reflex"):
        self.trace_id = str(uuid.uuid4())
        self.name = name
        self.spans = []

    def start(self, name, **attributes):
        span = Span(name, attributes=attributes, trace_id=self.trace_id)
        self.spans.append(span)
        return span

    def annotate_decision(self, record):
        span = self.start(
            "jev.decision",
            decision_id=record["decision_id"],
            model_version=record["model_version"],
            latency_ms=record["latency_ms"],
            kind="recommendation",
        )
        span.event("answers", ids=record.get("questions") or list(record.get("answers", {})))
        return span.close()
