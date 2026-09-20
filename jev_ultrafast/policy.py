"""Deterministic Beowulf policy. Jev does not get a vote on authority.

Whether approval is *required* belongs to policy, not to confidence::

    delete          -> HUMAN REQUIRED
    deploy          -> HUMAN REQUIRED
    money           -> HUMAN REQUIRED
    credential use  -> HUMAN REQUIRED
    release         -> HUMAN REQUIRED

Jev may return ``human_review_recommended``; only this module (plus human
gates) can require approval, dispatch work, or close a task.
"""

HUMAN_REQUIRED_KINDS = frozenset({"delete", "deploy", "money", "credential", "release"})

POLICY_VERSION = "policy-v1"


def requires_human(action_kind, context=None):
    kind = (action_kind or "").lower()
    if kind in HUMAN_REQUIRED_KINDS:
        return True
    context = context or {}
    flags = {str(v).lower() for v in context.values()} | {str(k).lower() for k in context}
    return bool(HUMAN_REQUIRED_KINDS & flags)


def route(route_recommendation, *, action_kind="unknown", context=None):
    """Combine a Jev recommendation with deterministic gates.

    Returns ``{"recommendation", "human_required", "dispatched_to"}``.
    Nothing here executes; Beowulf dispatches after this check.
    """
    human = requires_human(action_kind, context)
    return {
        "recommendation": route_recommendation,
        "human_required": human,
        "dispatched_to": "human" if human else route_recommendation,
        "policy_version": POLICY_VERSION,
    }
