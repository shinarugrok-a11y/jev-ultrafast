"""Offline providers for tests, evaluation runs, and replaying recorded decisions. They never call a paid API."""

import json
from pathlib import Path

from ..core.decision import state_hash
from .base import Evaluation


class StubProvider:
    """Returns answers from a callable or a fixed mapping. Used by tests and by the eval runner's dry runs."""

    name = "stub"

    def __init__(self, answers, model_version="stub-0"):
        self.answers = answers
        self.model_version = model_version
        self.calls = []

    def evaluate(self, state, questions):
        self.calls.append({"state": state, "questions": {k: q.to_request() for k, q in questions.items()}})
        answers = self.answers(state, questions) if callable(self.answers) else self.answers
        return Evaluation(answers=dict(answers), model_version=self.model_version, latency_ms=0)


class ReplayProvider:
    """Serves recorded answers keyed by the hash of (state, question requests). Unrecorded inputs fail loudly."""

    name = "replay"

    def __init__(self, path):
        self.path = Path(path)
        self.records = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    record = json.loads(line)
                    self.records[record["key"]] = record

    @staticmethod
    def key(state, questions):
        return state_hash({"state": state, "questions": {k: q.to_request() for k, q in questions.items()}})

    def record(self, state, questions, evaluation):
        key = self.key(state, questions)
        record = {
            "key": key,
            "answers": evaluation.answers,
            "model_version": evaluation.model_version,
            "latency_ms": evaluation.latency_ms,
            "usage": evaluation.usage,
        }
        self.records[key] = record
        with self.path.open("a") as handle:
            handle.write(json.dumps(record) + "\n")

    def evaluate(self, state, questions):
        record = self.records.get(self.key(state, questions))
        if record is None:
            raise LookupError("No recorded answer for this state and question set; record it with a live provider.")
        return Evaluation(record["answers"], record["model_version"], record["latency_ms"], record.get("usage", {}))
