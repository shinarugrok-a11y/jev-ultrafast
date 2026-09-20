"""Beowulf-facing System One gateway. Recommendations only.

Beowulf owns one local gateway so Pepper, Kimi, Cursor, and COMPSD do not
each hold a TypeSafe key or invent Jev prompts::

    POST /decision
    state + questions[] + policy_context -> answers + distributions +
        confidence + model_version + latency

The gateway logs every decision and never sends relay messages, switches
lanes, declares DONE, approves an artifact, or authorizes an operation.
"""

import time
import uuid

from .core.calibration import get_spec
from .core.decision import Decision, state_hash
from .core.validation import validate_choice

GATEWAY_VERSION = "gateway-v1"


class SystemOneGateway:
    def __init__(self, provider=None, *, model_version="jev-latest", policy_version="policy-v1"):
        self.provider = provider
        self.model_version = model_version
        self.policy_version = policy_version
        self.decisions = []

    def decide(self, state, questions, policy_context=None):
        started = time.perf_counter()
        request = {
            "model": self.model_version,
            "state": state,
            "questions": questions,
            "policy_context": policy_context or {},
        }
        if self.provider is None:
            import os

            from .model import post_json

            raw = post_json(
                "https://api.typesafe.ai/v1/systemone", os.environ["TYPESAFE_API_KEY"], _typesafe_body(request)
            )
        else:
            raw = self.provider(request)
        answers = {}
        for qid, question in questions.items():
            spec = get_spec(question["question_id"]) if "question_id" in question else None
            _ = spec  # Registry owns IDs; unknown IDs raise in get_spec when present.
            criteria = question["criteria"]
            answers[qid] = validate_choice(raw["answers"].get(qid, {}), set(criteria))
        decision = Decision(
            state,
            answers,
            model=raw.get("model", self.model_version),
            usage=raw.get("usage", {}),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
        record = {
            **decision.to_record(),
            "request_id": uuid.uuid4().hex,
            "gateway_version": GATEWAY_VERSION,
            "policy_version": self.policy_version,
            "policy_context": policy_context or {},
        }
        self.decisions.append(record)
        return {
            "answers": answers,
            "distributions": {qid: a["probabilities"] for qid, a in answers.items()},
            "confidence": {qid: a["confidence"] for qid, a in answers.items()},
            "model_version": record["model"],
            "policy_version": self.policy_version,
            "latency_ms": record["latency_ms"],
            "decision_id": record["decision_id"],
            "state_hash": record["state_hash"],
            "recommendations_only": True,
        }

    def log(self):
        return list(self.decisions)


def _typesafe_body(request):
    return {
        "model": request["state"].get("model", "jev-latest"),
        "state": request["state"],
        "questions": {
            qid: {k: v for k, v in question.items() if k != "question_id"}
            for qid, question in request["questions"].items()
        },
    }


def gateway_state_hash(state):
    return state_hash(state)
