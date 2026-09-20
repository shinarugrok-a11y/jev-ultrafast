"""Where authority lives.

Three rules, in order:

1. Some categories always require a human: delete, deploy, money, credential use, release. Jev does not get a
   vote here. The model may say ``human_review_recommended = 0.02``; the verdict is still ``human_required``.
2. Every probability that gates behavior is compared against a threshold from a checked-in calibration lock for
   that exact question ID. No lock, no automatic action: the verdict falls back to ``review``.
3. Only after both pass does a recommendation become ``act``, which still means "application code may now do the
   one thing it observed and consumed a decision for", never "Jev executed something".
"""

import fnmatch
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..core.calibration import MissingCalibration, load_locks, threshold_for

POLICY_VERSION = "policy.2026-09.v1"
HERE = Path(__file__).parent

HUMAN_REQUIRED = {
    "delete": "Deleting data, files, branches, resources, or messages.",
    "deploy": "Deploying or changing a running production system.",
    "money": "Spending, refunding, transferring, or committing money.",
    "credential": "Using, minting, rotating, or exposing credentials.",
    "release": "Publishing a release, package, or public announcement.",
}

COMMAND_PATTERNS = {
    "delete": (
        r"\brm\s+-[a-z]*r|\bgit\s+(push\s+.*--force|branch\s+-D|reset\s+--hard)"
        r"|\bdrop\s+(table|database)\b|\btruncate\b"
    ),
    "deploy": (
        r"\b(kubectl\s+(apply|delete|rollout)|terraform\s+(apply|destroy)|helm\s+(install|upgrade)"
        r"|fly\s+deploy|vercel\s+--prod)\b"
    ),
    "money": r"\b(stripe|charge|refund|payout|transfer)\b.*\b(create|post|send)\b",
    "credential": r"\b(aws\s+sts|gcloud\s+auth|vault\s+(write|read)|op\s+item|secrets?\s+(set|create)|api[_-]?key\s*=)",
    "release": r"\b(npm\s+publish|twine\s+upload|uv\s+publish|gh\s+release\s+create|git\s+push\s+.*--tags)\b",
}


@dataclass
class PolicyOutcome:
    verdict: str  # act | review | human_required | park
    reasons: list = field(default_factory=list)
    gates: dict = field(default_factory=dict)
    policy_version: str = POLICY_VERSION

    def to_dict(self):
        return asdict(self)


def categories_for_command(command):
    """Conservative, advisory classification of a shell command into HUMAN_REQUIRED categories."""
    text = " ".join(str(command).split())
    return sorted(c for c, pattern in COMMAND_PATTERNS.items() if re.search(pattern, text, re.IGNORECASE))


def forbidden_changes(paths, protections):
    """Deterministic: protected glob -> HUMAN_REQUIRED category, applied to changed paths. Jev is not consulted."""
    unknown = set(protections.values()) - set(HUMAN_REQUIRED)
    if unknown:
        raise ValueError(f"Protected paths must map to HUMAN_REQUIRED categories, not {sorted(unknown)}")
    matched = {}
    for path in paths:
        for pattern, category in protections.items():
            if fnmatch.fnmatch(path, pattern):
                matched.setdefault(category, []).append(path)
    return {category: sorted(set(paths)) for category, paths in sorted(matched.items())}


class Policy:
    def __init__(self, locks, gates, version=POLICY_VERSION):
        self.locks, self.gates, self.version = locks, gates, version

    def evaluate(self, recommendation, categories=(), model_version=None, extra_gates=None):
        outcome = PolicyOutcome("act", policy_version=self.version)
        human = sorted(set(categories) & set(HUMAN_REQUIRED))
        if human:
            # Rule 1. Return before consulting a single probability.
            outcome.verdict = "human_required"
            outcome.reasons = [f"{c}: {HUMAN_REQUIRED[c]}" for c in human]
            return outcome
        verdicts = {"act": 0, "park": 1, "review": 2}
        gates = {**self.gates.get("flags", {}), **(extra_gates or {})}
        for question_id, rule in gates.items():
            value = recommendation.flags.get(question_id)
            if value is None or not self._applies(rule, recommendation):
                continue
            try:
                threshold = threshold_for(question_id, self.locks, model_version)
            except MissingCalibration as error:
                outcome.gates[question_id] = {"value": value, "threshold": None, "tripped": True}
                outcome.reasons.append(str(error))
                outcome.verdict = "review"
                continue
            tripped = value >= threshold if rule["trip_when"] == "above" else value < threshold
            outcome.gates[question_id] = {"value": value, "threshold": threshold, "tripped": tripped}
            if tripped:
                outcome.reasons.append(f"{question_id}={value:.2f} tripped {rule['trip_when']} {threshold:.2f}")
                if verdicts[rule["verdict"]] > verdicts[outcome.verdict]:
                    outcome.verdict = rule["verdict"]
        question, confidence = recommendation.operation_question, recommendation.confidence
        rule = self.gates.get("confidence", {}).get(question) if question and confidence is not None else None
        if rule is not None:
            try:
                floor = threshold_for(question, self.locks, model_version)
            except MissingCalibration as error:
                outcome.reasons.append(str(error))
                outcome.verdict = "review"
                return outcome
            tripped = confidence < floor
            outcome.gates[question] = {"value": confidence, "threshold": floor, "tripped": tripped}
            if tripped:
                outcome.reasons.append(f"{question} confidence {confidence:.2f} < {floor:.2f}")
                if verdicts[rule["verdict"]] > verdicts[outcome.verdict]:
                    outcome.verdict = rule["verdict"]
        return outcome

    @staticmethod
    def _applies(rule, recommendation):
        only = rule.get("operations")
        return not only or recommendation.operation in only


def default_policy():
    locks = load_locks(HERE / "calibration_locks")
    gates = json.loads((HERE / "thresholds" / "gates.json").read_text())
    return Policy(locks, gates, gates.get("policy_version", POLICY_VERSION))
