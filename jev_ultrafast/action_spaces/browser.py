"""The original browser reflex, exposed through the universal contract without changing its request."""

import time

from ..core.questions import Question
from ..model import browser_request, resolve_browser_answers
from .base import ActionSpace, Recommendation


class BrowserActionSpace(ActionSpace):
    domain = "browser"

    def __init__(self, page, goal, history=()):
        self.page, self.goal, self.history = page, goal, list(history)
        self.body, self.operations, self.targets, self.controls = browser_request(page, goal, self.history)

    def state(self):
        return self.body["state"]

    def questions(self):
        questions = {}
        for key, raw in self.body["questions"].items():
            questions[key] = Question(f"browser.{key}.v1", raw["type"], raw["instructions"], raw["criteria"])
        return questions

    def speculative_heads(self):
        return {key for key in self.body["questions"] if key != "operation"}

    def resolve(self, answers):
        # resolve_browser_answers validates the operation head and only the matching target head.
        result = {"answers": answers, "model": "validated"}
        started = time.perf_counter()
        decision = resolve_browser_answers(result, self.body, self.operations, self.targets, self.controls, started)
        candidate = None
        if decision["target"] is not None:
            candidate = self.targets[decision["operation"]][decision["target"]]
        return Recommendation(
            domain=self.domain,
            operation=decision["operation"],
            operation_question="browser.operation.v1",
            target=decision["target"],
            candidate=candidate,
            confidence=decision["confidence"],
            probabilities=decision["probabilities"],
            answers={"choice": decision["choice"], "operation_probabilities": decision["operation_probabilities"]},
        )
