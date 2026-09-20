"""COMPSD/Beowulf receipts. File, transport, ACK, and proof remain distinct."""

import hashlib
import json
import re
import time
import uuid

SECRET_KEYS = re.compile(r"(key|token|secret|password|authorization|credential)", re.I)


def redact(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out[k] = "***" if SECRET_KEYS.search(str(k)) else redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class Receipt(dict):
    kinds = ("file", "transport", "ack", "execution", "visual", "test", "hook")

    def __init__(self, kind, **fields):
        if kind not in self.kinds:
            raise ValueError(f"Unknown receipt kind {kind}")
        payload = {
            "receipt_id": fields.pop("receipt_id", str(uuid.uuid4())),
            "kind": kind,
            "created_at": fields.pop("created_at", time.time()),
            **fields,
        }
        super().__init__(redact(payload))

    def digest(self):
        body = json.dumps(self, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()


def FileReceipt(*, path, digest, **fields):
    return Receipt("file", path=path, digest=digest, **fields)


def TransportReceipt(*, channel, message_id, **fields):
    return Receipt("transport", channel=channel, message_id=message_id, **fields)
