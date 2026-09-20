"""Core contract: versioned questions, typed validation, consume-once decisions, calibration records."""

import json

import pytest

from jev_ultrafast.core import (
    STANDARD_QUESTIONS,
    AlreadyConsumed,
    CalibrationRecord,
    DecisionLedger,
    MissingCalibration,
    Question,
    StaleDecision,
    brier_score,
    load_locks,
    state_hash,
    validate_answers,
    validate_noul,
    validate_score,
)
from jev_ultrafast.core.calibration import choice_brier, threshold_for
from jev_ultrafast.evidence import replay_ledger


@pytest.mark.parametrize("bad_id", ["executor", "routing.best_executor", "Routing.best.v1", "routing.best.v", "a.b.vx"])
def test_question_ids_must_be_versioned(bad_id):
    with pytest.raises(ValueError, match="domain.name.vN"):
        Question(bad_id, "noul", "Is it?")


def test_standard_questions_are_well_formed_and_versioned():
    for qid, q in STANDARD_QUESTIONS.items():
        assert q.id == qid and q.version >= 1
        body = q.to_request()
        assert body["type"] == q.type and "instructions" in body
    assert STANDARD_QUESTIONS["task.complexity.v1"].criteria[0].startswith("Trivial")
    assert len(STANDARD_QUESTIONS["task.consequence.v1"].criteria) == 6


def test_choice_can_only_be_narrowed_to_known_options():
    q = STANDARD_QUESTIONS["routing.best_executor.v2"]
    narrowed = q.with_criteria({"kimi_explore": q.criteria["kimi_explore"], "human": q.criteria["human"]})
    assert set(narrowed.criteria) == {"kimi_explore", "human"} and narrowed.id == q.id
    with pytest.raises(ValueError, match="not part of this question"):
        q.with_criteria({"chatgpt": "invented"})
    with pytest.raises(ValueError, match="only choice"):
        STANDARD_QUESTIONS["relay.needs_reply.v1"].with_criteria({})


@pytest.mark.parametrize(
    "answer",
    [
        {"score": 1.0, "probabilities": {"0": 0.0, "1": 1.0}, "confidence": 1.0},  # too few levels for a 3-level rubric
        {"score": 5, "probabilities": {"0": 0, "1": 0, "2": 1}, "confidence": 1},  # out of range
        {"score": 0.2, "probabilities": {"0": 0, "1": 0, "2": 1}, "confidence": 1},  # disagrees with distribution
        {"score": 2, "probabilities": {"0": 0, "1": 0, "2": 1}, "confidence": 3},  # bad confidence
        {"probabilities": {"0": 0, "1": 0, "2": 1}, "confidence": 1},  # missing score
        None,
    ],
)
def test_invalid_scores_are_rejected(answer):
    with pytest.raises(ValueError, match="Invalid TypeSafe"):
        validate_score(answer, ["low", "mid", "high"])


def test_valid_score_passes():
    answer = {"score": 1.05, "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05}, "confidence": 0.92}
    assert validate_score(answer, ["Calm", "Frustrated", "Very angry"]) is answer


@pytest.mark.parametrize("answer", [{"noul": 1.5}, {"noul": float("nan")}, {"noul": "0.5"}, {}, None])
def test_invalid_nouls_are_rejected(answer):
    with pytest.raises(ValueError, match="Invalid TypeSafe"):
        validate_noul(answer)


def test_validate_answers_requires_every_asked_question():
    questions = {"a": STANDARD_QUESTIONS["relay.needs_reply.v1"], "b": STANDARD_QUESTIONS["task.complexity.v1"]}
    with pytest.raises(ValueError, match="Invalid TypeSafe"):
        validate_answers(questions, {"a": {"noul": 0.4}})
    good = {"a": {"noul": 0.4}, "b": {"score": 2.0, "probabilities": {str(i): float(i == 2) for i in range(6)},
                                       "confidence": 1.0}, "extra": {"noul": 0.1}}
    assert set(validate_answers(questions, good)) == {"a", "b"}


def test_decision_is_consumed_once_against_the_evaluated_state(tmp_path):
    ledger = DecisionLedger(tmp_path / "log.jsonl")
    state = {"thread": [1, 2]}
    decision = ledger.issue("relay", state, {"q": {"noul": 0.9}}, "jev-test", 12)
    assert decision.state_hash == state_hash(state) and decision.consumed_at is None
    with pytest.raises(ValueError, match="unconsumed"):
        ledger.record_result(decision.decision_id, {"ok": True})
    with pytest.raises(StaleDecision):
        ledger.consume(decision.decision_id, {"thread": [1, 2, 3]}, {"op": "REPLY"})
    ledger.consume(decision.decision_id, state, {"op": "REPLY", "target": "2"})
    with pytest.raises(AlreadyConsumed):
        ledger.consume(decision.decision_id, state, {"op": "REPLY", "target": "2"})
    ledger.record_result(decision.decision_id, {"transport": "sent"})
    report = replay_ledger(tmp_path / "log.jsonl")
    assert report.ok and report.decisions == report.consumed == report.results == 1


def test_replay_detects_double_consumption_and_state_drift(tmp_path):
    ledger = DecisionLedger(tmp_path / "log.jsonl")
    d = ledger.issue("relay", {"a": 1}, {}, "jev-test", 1)
    ledger.consume(d.decision_id, {"a": 1}, {"op": "ACK"})
    forged = {**d.to_dict(), "event": "consumed", "at": 0, "state_hash": "different"}
    with (tmp_path / "log.jsonl").open("a") as handle:
        handle.write(json.dumps(forged) + "\n")
        handle.write(json.dumps({**d.to_dict(), "event": "result", "at": 0}) + "\n")
        handle.write(json.dumps({**d.to_dict(), "event": "result", "at": 0}) + "\n")
    report = replay_ledger(tmp_path / "log.jsonl")
    assert not report.ok
    assert any("consumed twice" in v for v in report.violations)
    assert any("two results" in v for v in report.violations)


def test_state_hash_is_canonical():
    assert state_hash({"b": 1, "a": [1, 2]}) == state_hash({"a": [1, 2], "b": 1})
    assert state_hash({"a": 1}) != state_hash({"a": 2})


def test_brier_scores():
    assert brier_score([1.0, 0.0], [True, False]) == 0
    assert brier_score([0.5, 0.5], [True, False]) == 0.25
    assert choice_brier([{"a": 1.0, "b": 0.0}], ["a"]) == 0
    assert choice_brier([{"a": 0.5, "b": 0.5}], ["a"]) == 0.5
    with pytest.raises(ValueError):
        brier_score([], [])
    with pytest.raises(ValueError, match="not one of the options"):
        choice_brier([{"a": 1.0}], ["zzz"])


def test_calibration_record_and_threshold_lookup(tmp_path):
    with pytest.raises(ValueError, match="needs fixtures"):
        CalibrationRecord("relay.needs_reply.v1", "jev-1", "policy", "calibrated", 0)
    with pytest.raises(ValueError, match="unknown calibration status"):
        CalibrationRecord("relay.needs_reply.v1", "jev-1", "policy", "maybe", 0)
    calibrated = CalibrationRecord("relay.needs_reply.v1", "jev-1", "policy", "calibrated", 40, 0.6, 0.11)
    (tmp_path / "relay.needs_reply.v1.json").write_text(json.dumps(calibrated.to_dict()))
    uncalibrated = CalibrationRecord("agent.should_wake.v1", "jev-1", "policy", "uncalibrated", 6)
    (tmp_path / "agent.should_wake.v1.json").write_text(json.dumps(uncalibrated.to_dict()))
    locks = load_locks(tmp_path)
    assert threshold_for("relay.needs_reply.v1", locks) == 0.6
    with pytest.raises(MissingCalibration):
        threshold_for("relay.needs_reply.v1", locks, model_version="jev-2")
    with pytest.raises(MissingCalibration):
        threshold_for("agent.should_wake.v1", locks)
    with pytest.raises(MissingCalibration):
        threshold_for("never.asked.v1", locks)
