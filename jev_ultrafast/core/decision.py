"""Consume-once decisions bound to the exact state they evaluated.

The browser agent consumes a decision before any mutation so a retry cannot double-click. This generalizes that
rule: a decision is usable once, against one state hash. If the state changed, re-evaluate. Results are recorded
against the consumed decision so a lost observation cannot erase the fact that something was executed.
"""

import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass, field


class StaleDecision(ValueError):
    """The state this decision evaluated is no longer the current state."""


class AlreadyConsumed(ValueError):
    """The decision was already used to request an action."""


def state_hash(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class Decision:
    decision_id: str
    domain: str
    state_hash: str
    question_ids: list
    answers: dict
    model_version: str
    latency_ms: int
    created_at: float
    consumed_at: float | None = None
    requested_action: dict | None = None
    result_receipt: dict | None = None
    usage: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class DecisionLedger:
    """In-memory ledger with an optional append-only JSONL log. One decision, one consumption, one result."""

    def __init__(self, log_path=None, clock=time.time):
        self.log_path = log_path
        self.clock = clock
        self.decisions = {}

    def issue(self, domain, state, answers, model_version, latency_ms, usage=None, question_ids=None):
        decision = Decision(
            decision_id=secrets.token_urlsafe(12),
            domain=domain,
            state_hash=state_hash(state),
            question_ids=sorted(question_ids or answers),
            answers=answers,
            model_version=model_version,
            latency_ms=latency_ms,
            created_at=self.clock(),
            usage=usage or {},
        )
        self.decisions[decision.decision_id] = decision
        self._log("issued", decision)
        return decision

    def consume(self, decision_id, current_state, requested_action):
        decision = self.decisions.get(decision_id)
        if decision is None:
            raise KeyError(f"Unknown decision {decision_id}")
        if decision.consumed_at is not None:
            raise AlreadyConsumed(f"Decision {decision_id} was already consumed")
        if state_hash(current_state) != decision.state_hash:
            raise StaleDecision(f"Decision {decision_id} evaluated a different state; re-evaluate")
        # Consume before the caller performs any side effect. A retry after this point cannot act twice.
        decision.consumed_at = self.clock()
        decision.requested_action = requested_action
        self._log("consumed", decision)
        return decision

    def record_result(self, decision_id, receipt):
        decision = self.decisions[decision_id]
        if decision.consumed_at is None:
            raise ValueError("Cannot record a result for an unconsumed decision")
        decision.result_receipt = receipt
        self._log("result", decision)
        return decision

    def _log(self, event, decision):
        if self.log_path:
            with open(self.log_path, "a") as handle:
                handle.write(json.dumps({"event": event, "at": self.clock(), **decision.to_dict()}) + "\n")
