"""Replay a logged recommendation against consume-once rules without calling a model."""

from ..core.decision import DecisionLedger, state_hash


def replay_decision(record, observed_state, requested_action):
    """Re-bind a prior recommendation to current state. Does not execute."""
    ledger = DecisionLedger()
    ledger.records[record["decision_id"]] = dict(record, consumed_at=None, requested_action=None, result_receipt=None)
    consumed = ledger.consume(record["decision_id"], observed_state, requested_action)
    return {
        "decision_id": consumed["decision_id"],
        "state_hash": state_hash(observed_state),
        "replayed": True,
        "kind": "recommendation",
        "requested_action": requested_action,
    }
