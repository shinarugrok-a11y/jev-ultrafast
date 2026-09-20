"""Consume-once decisions bound to the exact state they evaluated."""

import hashlib
import json
import time
import uuid


class StaleDecision(ValueError):
    """The observed state no longer matches the decision's state hash."""


class AlreadyConsumed(ValueError):
    """A decision may execute at most once."""


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def state_hash(state, *, ignore=("screenshot",)):
    if isinstance(state, dict):
        payload = {k: v for k, v in state.items() if k not in ignore}
    else:
        payload = state
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


class DecisionLedger:
    """A decision is usable once, against exactly the state it evaluated."""

    def __init__(self):
        self.records = {}

    def remember(
        self,
        *,
        state,
        answers,
        questions,
        model_version,
        policy_version,
        latency_ms,
        usage=None,
        extra=None,
    ):
        record = {
            "decision_id": str(uuid.uuid4()),
            "state_hash": state_hash(state),
            "created_at": time.time(),
            "consumed_at": None,
            "requested_action": None,
            "result_receipt": None,
            "answers": answers,
            "questions": list(questions),
            "model_version": model_version,
            "policy_version": policy_version,
            "latency_ms": latency_ms,
            "usage": usage or {},
            "kind": "recommendation",
            **(extra or {}),
        }
        self.records[record["decision_id"]] = record
        return record

    def consume(self, decision_id, observed_state, requested_action):
        record = self.records.get(decision_id)
        if record is None:
            raise KeyError(f"Unknown decision {decision_id}")
        # Consume before any mutation so a retry cannot double-execute.
        if record["consumed_at"] is not None:
            raise AlreadyConsumed("Decision already consumed; re-evaluate instead of retrying")
        observed = state_hash(observed_state)
        if observed != record["state_hash"]:
            raise StaleDecision("State changed since the decision. Choose again.")
        record["consumed_at"] = time.time()
        record["requested_action"] = requested_action
        return record

    def attach_receipt(self, decision_id, receipt):
        record = self.records[decision_id]
        if record["consumed_at"] is None:
            raise ValueError("Receipts attach only after a decision is consumed")
        if record["result_receipt"] is not None:
            raise AlreadyConsumed("A consumed decision already has a result receipt")
        record["result_receipt"] = receipt
        return record
