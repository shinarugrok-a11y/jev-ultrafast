"""Deterministic policy: humans keep their categories, thresholds come only from calibration locks."""

import pytest

from jev_ultrafast.action_spaces.base import Recommendation
from jev_ultrafast.core import CalibrationRecord
from jev_ultrafast.policy import HUMAN_REQUIRED, Policy, categories_for_command, default_policy, forbidden_changes

GATES = {
    "flags": {
        "task.human_review_recommended.v4": {"trip_when": "above", "verdict": "review"},
        "task.likely_duplicate_work.v1": {"trip_when": "above", "verdict": "park"},
        "relay.needs_reply.v1": {"trip_when": "below", "verdict": "park", "operations": ["REPLY"]},
    },
    "confidence": {"relay.next_operation.v1": {"verdict": "review"}},
}


def lock(qid, threshold, model="jev-1.13.0"):
    return CalibrationRecord(qid, model, "policy.test", "calibrated", 40, threshold, 0.08, 0.93)


def calibrated_policy():
    locks = {
        qid: lock(qid, t)
        for qid, t in {
            "task.human_review_recommended.v4": 0.6,
            "task.likely_duplicate_work.v1": 0.7,
            "relay.needs_reply.v1": 0.5,
            "relay.next_operation.v1": 0.4,
        }.items()
    }
    return Policy(locks, GATES)


def recommendation(operation="REPLY", confidence=0.8, **flags):
    return Recommendation("relay", operation, "relay.next_operation.v1", flags=flags, confidence=confidence)


def test_human_required_categories_ignore_every_probability():
    outcome = calibrated_policy().evaluate(
        recommendation(**{"task.human_review_recommended.v4": 0.01}), categories=["deploy", "unrelated"]
    )
    assert outcome.verdict == "human_required" and outcome.gates == {}
    assert outcome.reasons == [f"deploy: {HUMAN_REQUIRED['deploy']}"]


def test_uncalibrated_question_falls_back_to_review():
    policy = Policy({}, GATES)
    outcome = policy.evaluate(recommendation(**{"task.human_review_recommended.v4": 0.05}))
    assert outcome.verdict == "review"
    assert any("no calibrated threshold" in r for r in outcome.reasons)


def test_default_policy_is_conservative_until_a_live_calibration_run():
    policy = default_policy()
    assert policy.locks and all(r.status == "uncalibrated" for r in policy.locks.values())
    outcome = policy.evaluate(recommendation(**{"task.human_review_recommended.v4": 0.0}))
    assert outcome.verdict == "review"


def test_calibrated_gates_act_or_trip_by_their_own_thresholds():
    policy = calibrated_policy()
    flags = {"task.human_review_recommended.v4": 0.3, "task.likely_duplicate_work.v1": 0.2, "relay.needs_reply.v1": 0.9}
    assert policy.evaluate(recommendation(**flags)).verdict == "act"
    review = policy.evaluate(recommendation(**{**flags, "task.human_review_recommended.v4": 0.61}))
    assert review.verdict == "review" and review.gates["task.human_review_recommended.v4"]["tripped"]
    park = policy.evaluate(recommendation(**{**flags, "task.likely_duplicate_work.v1": 0.75}))
    assert park.verdict == "park"
    # review outranks park when both trip
    both = policy.evaluate(
        recommendation(**{**flags, "task.likely_duplicate_work.v1": 0.75, "task.human_review_recommended.v4": 0.9})
    )
    assert both.verdict == "review"


def test_operation_scoped_gate_only_applies_to_its_operation():
    policy = calibrated_policy()
    flags = {"task.human_review_recommended.v4": 0.1, "task.likely_duplicate_work.v1": 0.1, "relay.needs_reply.v1": 0.2}
    assert policy.evaluate(recommendation("REPLY", **flags)).verdict == "park"
    assert policy.evaluate(recommendation("IGNORE", **flags)).verdict == "act"


def test_confidence_floor_uses_the_operation_question_lock():
    policy = calibrated_policy()
    flags = {"task.human_review_recommended.v4": 0.1}
    assert policy.evaluate(recommendation(confidence=0.39, **flags)).verdict == "review"
    assert policy.evaluate(recommendation(confidence=0.41, **flags)).verdict == "act"
    other_model = policy.evaluate(recommendation(confidence=0.9, **flags), model_version="jev-2.0.0")
    assert other_model.verdict == "review" and "calibrated for jev-1.13.0" in " ".join(other_model.reasons)


@pytest.mark.parametrize(
    "command, expected",
    [
        ("rm -rf build/", ["delete"]),
        ("git push origin main --force", ["delete"]),
        ("kubectl apply -f prod.yaml", ["deploy"]),
        ("npm publish", ["release"]),
        ("vault read secret/relay", ["credential"]),
        ("uv run pytest", []),
        ("ls -la", []),
    ],
)
def test_command_categories_are_conservative_and_advisory(command, expected):
    assert categories_for_command(command) == expected


def test_forbidden_changes_map_protected_paths_to_human_categories():
    matches = forbidden_changes(
        ["cli/receipts.py", "deploy/prod.yaml", ".env", "infra/deploy/a.tf"],
        {"deploy/*": "deploy", "**/deploy/*": "deploy", "*.env": "credential"},
    )
    assert matches == {"credential": [".env"], "deploy": ["deploy/prod.yaml", "infra/deploy/a.tf"]}
    assert forbidden_changes(["README.md"], {"deploy/*": "deploy"}) == {}
    with pytest.raises(ValueError, match="HUMAN_REQUIRED"):
        forbidden_changes(["x"], {"*": "scary"})
