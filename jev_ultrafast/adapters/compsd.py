"""COMPSD packet shape: identity, reply_to, receipts, evidence. No transport here."""

from ..evidence.receipts import redact


class Packet(dict):
    def __init__(self, **fields):
        required = {"packet_id", "identity", "text"}
        missing = required - set(fields)
        if missing:
            raise ValueError(f"COMPSD packet missing {sorted(missing)}")
        super().__init__(
            packet_id=fields["packet_id"],
            identity=fields["identity"],
            reply_to=fields.get("reply_to"),
            text=fields["text"],
            receipts=list(fields.get("receipts") or []),
            evidence=list(fields.get("evidence") or []),
            prior_ids=list(fields.get("prior_ids") or []),
        )

    def redacted(self):
        return redact(dict(self))
