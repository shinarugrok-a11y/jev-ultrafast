"""The universal ActionSpace contract.

The browser agent asks "which operation?" and "which compatible element?" in one request, then consumes only the
target head for the chosen operation. Every domain here keeps that shape: observed candidates get indices, the
model chooses among indices, and code maps the index back to the observed thing. The model never emits
selectors, coordinates, message bodies, or executable code. Whatever comes out is a recommendation.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

from ..core.validation import validate_answers, validate_choice


@dataclass
class Recommendation:
    domain: str
    operation: str
    operation_question: str | None = None
    target: str | None = None
    candidate: dict | None = None
    confidence: float | None = None
    probabilities: dict = field(default_factory=dict)
    flags: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    answers: dict = field(default_factory=dict)
    authority: str = "recommendation"

    def to_dict(self):
        return asdict(self)


class ActionSpace(ABC):
    domain = "abstract"

    @abstractmethod
    def state(self):
        """Structured state for the model. Untrusted text is data, never instructions."""

    @abstractmethod
    def questions(self):
        """Request key -> Question. Speculative heads are fine; resolve() decides which ones count."""

    @abstractmethod
    def resolve(self, answers):
        """Validated answers -> Recommendation bound to observed candidates."""

    def speculative_heads(self):
        """Request keys that only matter for some operations. resolve() validates the one it actually uses."""
        return set()

    def validate(self, answers):
        questions = self.questions()
        required = {k: q for k, q in questions.items() if k not in self.speculative_heads()}
        validated = validate_answers(required, answers)
        for key in self.speculative_heads():
            if key in answers:
                validated[key] = answers[key]
        return validated

    def use_head(self, key, answers):
        """Validate a speculative choice head at the moment its operation was selected."""
        return validate_choice(answers.get(key), self.questions()[key].criteria)

    @staticmethod
    def flags_and_scores(questions, answers):
        flags = {k: answers[k]["noul"] for k, q in questions.items() if q.type == "noul" and k in answers}
        scores = {k: answers[k]["score"] for k, q in questions.items() if q.type == "score" and k in answers}
        return flags, scores


def evaluate_space(space, provider, ledger=None):
    """One provider request, validation, resolution, and (optionally) a ledger entry bound to the state hash."""
    state, questions = space.state(), space.questions()
    started = time.perf_counter()
    evaluation = provider.evaluate(state, questions)
    answers = space.validate(evaluation.answers)
    recommendation = space.resolve(answers)
    decision = None
    if ledger is not None:
        decision = ledger.issue(
            space.domain,
            state,
            answers,
            evaluation.model_version,
            evaluation.latency_ms or round((time.perf_counter() - started) * 1000),
            usage=evaluation.usage,
            question_ids=[q.id for q in questions.values()],
        )
    return recommendation, decision, evaluation
