"""OTel-shaped spans in JSONL. Decisions, verdicts, and executions are annotated onto spans, never inferred."""

import json
import secrets
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field


@dataclass
class Span:
    trace_id: str
    span_id: str
    name: str
    parent_span_id: str | None = None
    start: float = field(default_factory=time.time)
    end: float | None = None
    attributes: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    status: str = "unset"

    def set(self, **attributes):
        self.attributes.update(attributes)

    def event(self, name, **attributes):
        self.events.append({"name": name, "at": time.time(), **attributes})

    def to_dict(self):
        return asdict(self)


class TraceWriter:
    def __init__(self, path=None, trace_id=None):
        self.path = path
        self.trace_id = trace_id or secrets.token_hex(16)
        self.spans = []

    @contextmanager
    def span(self, name, parent=None, **attributes):
        span = Span(self.trace_id, secrets.token_hex(8), name, parent.span_id if parent else None)
        span.set(**attributes)
        try:
            yield span
            span.status = "ok" if span.status == "unset" else span.status
        except Exception as error:
            span.status = "error"
            span.event("exception", type=type(error).__name__, message=str(error))
            raise
        finally:
            span.end = time.time()
            self.spans.append(span)
            if self.path:
                with open(self.path, "a") as handle:
                    handle.write(json.dumps(span.to_dict()) + "\n")

    @staticmethod
    def annotate_decision(span, decision, recommendation=None, outcome=None):
        span.set(
            **{
                "jev.decision_id": decision.decision_id,
                "jev.domain": decision.domain,
                "jev.state_hash": decision.state_hash,
                "jev.model_version": decision.model_version,
                "jev.latency_ms": decision.latency_ms,
                "jev.questions": decision.question_ids,
            }
        )
        if recommendation is not None:
            span.set(
                **{
                    "jev.operation": recommendation.operation,
                    "jev.target": recommendation.target,
                    "jev.confidence": recommendation.confidence,
                    "jev.flags": recommendation.flags,
                    "jev.scores": recommendation.scores,
                }
            )
        if outcome is not None:
            span.set(**{"policy.verdict": outcome.verdict, "policy.version": outcome.policy_version})
            span.set(**{"policy.reasons": outcome.reasons})
