"""Authority that Jev does not get a vote on.

delete, deploy, money, credential use, and release require a human.
`human_review_recommended` is a Jev noul. `human_approval_required` is not.
"""

HUMAN_REQUIRED = frozenset({"delete", "deploy", "money", "credential_use", "release"})

JEV_MUST_NOT = frozenset(
    {
        "send_relay",
        "resend_relay",
        "switch_lane",
        "declare_done",
        "approve_artifact",
        "authorize_operation",
    }
)


def approval_required(action_kind):
    """True when policy, not Jev, demands a human. Jev's answers are ignored."""
    return action_kind in HUMAN_REQUIRED


def jev_must_not(action_kind):
    return action_kind in JEV_MUST_NOT
