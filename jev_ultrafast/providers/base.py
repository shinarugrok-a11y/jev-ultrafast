"""The provider contract every System One backend must satisfy."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Evaluation:
    answers: dict
    model_version: str
    latency_ms: int
    usage: dict = field(default_factory=dict)
    request: dict | None = None


class SystemOneProvider(Protocol):
    name: str

    def evaluate(self, state, questions) -> Evaluation:
        """Evaluate ``questions`` (id -> Question) against ``state``. Answers are raw and still need validation."""
