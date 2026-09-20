"""Consume-once decisions generalized from the browser loop.

A decision is usable once against exactly the state it evaluated:
``decision_id`` identifies the judgment, ``state_hash`` binds it to observed
state, and ``consumed_at`` marks single use before any mutation. A retry must
re-evaluate instead of re-executing. Jev judges; code owns execution.
"""

import hashlib
import json
import time
import uuid


def state_hash(state):
    canonical = json.dumps(state, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class Decision:
    def __init__(self, state, answers, *, model="unknown", usage=None, latency_ms=0):
        self.decision_id = uuid.uuid4().hex
        self.state_hash = state_hash(state)
        self.state = state
        self.answers = answers
        self.model = model
        self.usage = usage or {}
        self.latency_ms = latency_ms
        self.created_at = time.time()
        self.consumed_at = None

    def consume(self, state):
        """Mark this decision used. Raises when reused or when state moved on."""
        if self.consumed_at is not None:
            raise ValueError("Decision already consumed; re-evaluate before acting.")
        if state_hash(state) != self.state_hash:
            raise ValueError("State changed since the decision. Observe again.")
        self.consumed_at = time.time()
        return self.answers

    def to_record(self):
        return {
            "decision_id": self.decision_id,
            "state_hash": self.state_hash,
            "answers": self.answers,
            "model": self.model,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "consumed_at": self.consumed_at,
        }


def consume_once(record, state):
    """Consume a plain decision record once, before any mutation or model call."""
    if record.get("consumed_at") is not None:
        raise ValueError("Decision already consumed; re-evaluate before acting.")
    if state_hash(state) != record.get("state_hash"):
        raise ValueError("State changed since the decision. Observe again.")
    record["consumed_at"] = time.time()
    return record
