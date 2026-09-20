"""Relay judgments. Jev never sends, resends, or switches lanes."""

from ..core.catalog import EXECUTORS
from ..core.questions import choice_question, noul_question
from .base import ActionSpace, BoundAction, ObservedState

OPERATIONS = {
    "HOLD": "Keep the packet parked. Do not send anything.",
    "RECOMMEND_REPLY": "A reply appears warranted. Beowulf/policy still decides whether to send.",
    "RECOMMEND_ROUTE": "Recommend an executor. Do not dispatch.",
    "FLAG_DUPLICATE": "This looks like a duplicate of earlier work.",
    "REQUEST_CLARIFICATION": "The packet is missing identity, goal, or evidence needed to proceed.",
}


class RelayActionSpace(ActionSpace):
    domain = "relay"
    forbidden = ("send", "resend", "switch_lane", "authorize")

    def observe(self, raw_state):
        packet = raw_state.get("packet", raw_state)
        return ObservedState(
            domain=self.domain,
            packet_id=packet.get("packet_id") or packet.get("id"),
            identity=packet.get("identity"),
            reply_to=packet.get("reply_to"),
            text=packet.get("text") or packet.get("body"),
            receipts=packet.get("receipts") or [],
            prior_ids=packet.get("prior_ids") or [],
            fingerprint=raw_state.get("fingerprint"),
        )

    def questions(self, observed, *, goal="", history=None, extra=None):
        return {
            "operation": choice_question(
                OPERATIONS, "Which bounded relay judgment fits this packet? Never send or resend."
            ),
            "relay.needs_reply.v1": noul_question(
                "Does this relay packet warrant a reply rather than silence or a hold?",
                {"true": "A reply would be useful.", "false": "No reply should be sent from this judgment."},
            ),
            "task.likely_duplicate_work.v1": noul_question(
                "Does this look like work that was already requested or completed?",
                {"true": "A prior packet already covers this.", "false": "This appears to be new work."},
            ),
            "routing.best_executor.v2": choice_question(
                EXECUTORS,
                "If a worker is needed, which executor should Beowulf consider? Recommendation only.",
            ),
        }

    def bind(self, answers, observed):
        operation = answers["operation"]["choice"]
        return BoundAction(
            domain=self.domain,
            choice=operation,
            operation=operation,
            target=None,
            packet_id=observed.get("packet_id"),
            needs_reply=answers["relay.needs_reply.v1"]["noul"],
            likely_duplicate=answers["task.likely_duplicate_work.v1"]["noul"],
            recommended_executor=answers["routing.best_executor.v2"]["choice"],
            confidence=answers["operation"]["confidence"],
            probabilities=answers["operation"]["probabilities"],
            kind="recommendation",
        )
