"""COMPSD records. Identity, reply_to, and relay IDs travel with every receipt; duplicates are detected in code."""

import json
from pathlib import Path

from ..evidence.receipts import Receipt


class CompsdRecorder:
    def __init__(self, path=None, identity="beowulf"):
        self.path = Path(path) if path else None
        self.identity = identity
        self.receipts = []
        self.seen_relay_ids = set()

    def seen(self, relay_id):
        """True when this relay ID was already recorded. Deterministic dedupe before any send."""
        return relay_id in self.seen_relay_ids

    def record(self, kind, subject, evidence=None, issuer=None, parent=None, relay_id=None, reply_to=None):
        if relay_id is not None:
            if self.seen(relay_id):
                raise ValueError(f"Relay id {relay_id} was already recorded; refusing to record it twice")
            self.seen_relay_ids.add(relay_id)
        receipt = Receipt(
            kind,
            subject,
            issuer or self.identity,
            {**(evidence or {}), "relay_id": relay_id, "reply_to": reply_to, "identity": self.identity},
            parent,
        )
        self.receipts.append(receipt)
        if self.path:
            with self.path.open("a") as handle:
                handle.write(json.dumps(receipt.to_dict()) + "\n")
        return receipt

    def for_subject(self, subject):
        return [r for r in self.receipts if r.subject == subject]
