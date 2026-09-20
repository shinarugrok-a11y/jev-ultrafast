"""Evidence receipts, traces, and replay. Completion stays separate from Jev.

Jev can answer ``claim_supported? 0.94``; it must not set DONE. Completion
requires evidence (tests, files, visual receipts), a validated receipt chain,
and human gates where policy demands. A decision is usable once against
exactly the state it evaluated; a changed state re-evaluates.
"""

import time
import uuid


def receipt(*, decision_id, state_hash, requested_action, result="executed"):
    return {
        "receipt_id": uuid.uuid4().hex,
        "decision_id": decision_id,
        "state_hash": state_hash,
        "consumed_at": time.time(),
        "requested_action": requested_action,
        "result": result,
    }


class Trace:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append({**event, "at": time.time()})
        return self.events[-1]

    def verify_chain(self):
        """Every execution event must reference a consumed decision for the same state."""
        consumed = {(e["decision_id"], e["state_hash"]) for e in self.events if e.get("consumed_at")}
        for event in self.events:
            if event.get("type") == "executed" and (event["decision_id"], event["state_hash"]) not in consumed:
                return False
        return True

    def replay(self, decision_record, state):
        if decision_record.get("consumed_at") is None:
            raise ValueError("Decision was never consumed; nothing to replay.")
        if decision_record.get("state_hash") != state_hash_of(state):
            raise ValueError("Replay state differs from the decided state.")
        return dict(decision_record)


def state_hash_of(state):
    from .core.decision import state_hash

    return state_hash(state)
