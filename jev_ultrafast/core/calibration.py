"""Per-question calibration locks. Never a magical global confidence cutoff."""

import json
from pathlib import Path

LOCK_DIR = Path(__file__).resolve().parent.parent / "policy" / "calibration_locks"


class CalibrationLock:
    def __init__(self, record):
        required = {"question_id", "model_version", "policy_version", "threshold"}
        missing = required - set(record)
        if missing:
            raise ValueError(f"Calibration lock missing {sorted(missing)}")
        if record["threshold"].get("kind") == "global_confidence":
            raise ValueError("Global confidence cutoffs are not allowed; lock a specific question")
        self.record = record

    @property
    def question_id(self):
        return self.record["question_id"]

    @property
    def threshold(self):
        return self.record["threshold"]

    def as_dict(self):
        return dict(self.record)


def load_lock(question_id, *, directory=LOCK_DIR):
    path = Path(directory) / f"{question_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No calibration lock for {question_id}")
    return CalibrationLock(json.loads(path.read_text()))


def brier_score(predictions, outcomes):
    if len(predictions) != len(outcomes) or not predictions:
        raise ValueError("Brier score needs paired predictions and outcomes")
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)


def apply_lock(lock, answer, *, model_version=None):
    """Return whether policy may use this answer, using the lock's own threshold."""
    record = lock.record if isinstance(lock, CalibrationLock) else lock
    threshold = record["threshold"]
    if model_version and model_version != record["model_version"]:
        return {
            "accepted": False,
            "reason": "model_version_mismatch",
            "fallback": threshold.get("fallback"),
            "question_id": record["question_id"],
        }
    kind = threshold["kind"]
    if kind == "choice_probability":
        choice = answer["choice"]
        probability = answer["probabilities"][choice]
        confidence = answer["confidence"]
        accepted = probability >= threshold["min_probability"] and confidence >= threshold["min_confidence"]
        return {
            "accepted": accepted,
            "choice": choice,
            "probability": probability,
            "confidence": confidence,
            "fallback": None if accepted else threshold.get("fallback"),
            "question_id": record["question_id"],
        }
    if kind == "noul":
        value = answer["noul"]
        accepted = value >= threshold["min_noul"]
        return {
            "accepted": accepted,
            "noul": value,
            "fallback": None if accepted else threshold.get("fallback"),
            "question_id": record["question_id"],
        }
    if kind == "score":
        value = answer["score"]
        accepted = value >= threshold["min_score"]
        return {
            "accepted": accepted,
            "score": value,
            "fallback": None if accepted else threshold.get("fallback"),
            "question_id": record["question_id"],
        }
    raise ValueError(f"Unknown threshold kind {kind}")
