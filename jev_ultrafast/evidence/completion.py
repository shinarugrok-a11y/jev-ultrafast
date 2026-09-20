"""Independent completion. Jev can score claim_supported; it cannot set DONE."""

from ..core.calibration import apply_lock, load_lock

REQUIRED_KINDS = {"file", "test"}


class CompletionError(ValueError):
    """The receipt chain does not prove the claimed outcome."""


def verify_completion(claim, receipts, answers=None, *, action_kind=None, lock=None):
    """Beowulf-facing verifier. A Jev DONE/claim is never sufficient."""
    kinds = {r.get("kind") for r in receipts}
    missing = REQUIRED_KINDS - kinds
    claim_noul = None
    if answers and "completion.claim_supported.v3" in answers:
        claim_noul = answers["completion.claim_supported.v3"]["noul"]
        lock = lock or load_lock("completion.claim_supported.v3")
        gated = apply_lock(lock, answers["completion.claim_supported.v3"])
        supported = gated["accepted"]
    else:
        supported = False
        gated = None
    result = {
        "closed": False,
        "claim": claim,
        "claim_supported": claim_noul,
        "gate": gated,
        "missing_evidence": sorted(missing),
        "receipt_kinds": sorted(kinds),
        "human_gate": action_kind in {"delete", "deploy", "money", "credential_use", "release"},
        "jev_done": False,
        "reason": "incomplete",
    }
    if result["human_gate"]:
        result["reason"] = "HUMAN REQUIRED"
        return result
    if missing:
        result["reason"] = "missing_evidence"
        return result
    if not supported:
        result["reason"] = "claim_unsupported"
        return result
    result["closed"] = True
    result["reason"] = "receipt_chain"
    return result
