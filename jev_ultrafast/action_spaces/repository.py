"""Repository change screening. Jev does not write git, merge, or push."""

from ..core.questions import choice_question, noul_question, score_question
from .base import ActionSpace, BoundAction, ObservedState

OPERATIONS = {
    "ALLOW_REVIEW": "The change looks in-bounds for later review.",
    "FLAG_RISK": "The change should be treated as higher risk.",
    "FLAG_FORBIDDEN": "The change appears to touch forbidden paths or secrets.",
    "NEEDS_SPLIT": "The change mixes unrelated concerns and should be split.",
}

SCORE_LEVELS = ["0 none", "1 very low", "2 low", "3 moderate", "4 high", "5 extreme"]


class RepoActionSpace(ActionSpace):
    domain = "repository"
    forbidden = ("commit", "push", "merge", "force_push", "write")

    def observe(self, raw_state):
        diff = raw_state.get("diff", raw_state)
        return ObservedState(
            domain=self.domain,
            files=diff.get("files") or [],
            summary=diff.get("summary") or "",
            forbidden_hits=diff.get("forbidden_hits") or [],
            fingerprint=raw_state.get("fingerprint"),
        )

    def questions(self, observed, *, goal="", history=None, extra=None):
        return {
            "operation": choice_question(OPERATIONS, "Screen this repository change. Do not commit, push, or merge."),
            "repo.change_risk.v2": score_question(SCORE_LEVELS, "How risky are the proposed repository changes?"),
            "task.requires_repository_write.v1": noul_question(
                "Does the requested outcome require writing to a repository?",
                {"true": "A patch is part of the work.", "false": "Read-only analysis is enough."},
            ),
            "task.human_review_recommended.v1": noul_question(
                "Would a human review of this change be useful?",
                {"true": "Review is recommended.", "false": "Ordinary policy can continue."},
            ),
        }

    def bind(self, answers, observed):
        operation = answers["operation"]["choice"]
        return BoundAction(
            domain=self.domain,
            choice=operation,
            operation=operation,
            target=None,
            risk=answers["repo.change_risk.v2"]["score"],
            requires_write=answers["task.requires_repository_write.v1"]["noul"],
            human_review_recommended=answers["task.human_review_recommended.v1"]["noul"],
            forbidden_hits=observed.get("forbidden_hits") or [],
            confidence=answers["operation"]["confidence"],
            probabilities=answers["operation"]["probabilities"],
            kind="recommendation",
        )
