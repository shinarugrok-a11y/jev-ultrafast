"""Receipt kinds and chain verification.

Four different things get confused as "done": a file was written (file), a message left us (transport), the
other side confirmed receipt (ack), and the external outcome actually happened (proof). Completion needs the
whole chain, and the proof must come from someone other than the party claiming completion.
"""

import secrets
import time
from dataclasses import asdict, dataclass, field

KINDS = ("file", "transport", "ack", "proof")


@dataclass(frozen=True)
class Receipt:
    kind: str
    subject: str
    issuer: str
    evidence: dict = field(default_factory=dict)
    parent: str | None = None
    at: float = field(default_factory=time.time)
    receipt_id: str = field(default_factory=lambda: secrets.token_urlsafe(9))

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"Unknown receipt kind {self.kind!r}; expected one of {KINDS}")
        if not self.subject or not self.issuer:
            raise ValueError("A receipt needs a subject and an issuer")

    def to_dict(self):
        return asdict(self)


@dataclass
class ChainResult:
    complete: bool
    missing: list
    problems: list

    def to_dict(self):
        return asdict(self)


def verify_chain(receipts, subject, claimant, required=KINDS):
    """Deterministic. Missing kinds, wrong subjects, or a self-issued proof all fail."""
    relevant = [r for r in receipts if r.subject == subject]
    present = {r.kind for r in relevant}
    missing = [k for k in required if k not in present]
    problems = []
    for r in relevant:
        if r.kind == "proof" and r.issuer == claimant:
            problems.append(f"proof {r.receipt_id} was issued by the claimant {claimant!r}")
    by_id = {r.receipt_id: r for r in relevant}
    for r in relevant:
        if r.parent and r.parent not in by_id:
            problems.append(f"{r.kind} {r.receipt_id} references unknown parent {r.parent}")
    sequence = [r.kind for r in sorted(relevant, key=lambda r: r.at) if r.kind in required]
    if sequence != sorted(sequence, key=required.index):
        problems.append("receipts are out of order for their kinds")
    return ChainResult(not missing and not problems, missing, problems)
