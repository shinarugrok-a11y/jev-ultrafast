"""Calibration records: the only legitimate source of a threshold.

There is no global ``confidence > 0.85``. Every question that gates behavior carries a checked-in record with
the labeled fixture count, Brier score or error, the threshold chosen, and the model and policy versions it was
measured under. A question without a calibrated record is not actionable; policy routes it to review.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


class MissingCalibration(LookupError):
    """No calibrated record exists for this question, model, and policy version."""


@dataclass(frozen=True)
class CalibrationRecord:
    question_id: str
    model_version: str
    policy_version: str
    status: str  # "calibrated" or "uncalibrated"
    fixtures: int
    threshold: float | None = None
    brier: float | None = None
    accuracy: float | None = None
    mean_absolute_error: float | None = None
    measured_at: str | None = None
    notes: str = ""

    def __post_init__(self):
        if self.status not in {"calibrated", "uncalibrated"}:
            raise ValueError(f"{self.question_id}: unknown calibration status {self.status!r}")
        if self.status == "calibrated" and (self.fixtures < 1 or self.threshold is None or self.brier is None):
            raise ValueError(f"{self.question_id}: a calibrated record needs fixtures, a threshold, and a Brier score")

    def to_dict(self):
        return asdict(self)


def brier_score(predictions, outcomes):
    """Mean squared error between predicted probabilities and 0/1 outcomes. Lower is better; 0.25 is chance."""
    pairs = list(zip(predictions, outcomes, strict=True))
    if not pairs:
        raise ValueError("Brier score needs at least one labeled prediction")
    return sum((p - float(o)) ** 2 for p, o in pairs) / len(pairs)


def choice_brier(distributions, labels):
    """Multi-class Brier: sum over options of squared error, averaged over fixtures."""
    pairs = list(zip(distributions, labels, strict=True))
    if not pairs:
        raise ValueError("Brier score needs at least one labeled prediction")
    total = 0.0
    for distribution, label in pairs:
        if label not in distribution:
            raise ValueError(f"Label {label!r} is not one of the options")
        total += sum((p - float(option == label)) ** 2 for option, p in distribution.items())
    return total / len(pairs)


def load_locks(directory):
    records = {}
    for path in sorted(Path(directory).glob("*.json")):
        record = CalibrationRecord(**json.loads(path.read_text()))
        records[record.question_id] = record
    return records


def threshold_for(question_id, locks, model_version=None):
    record = locks.get(question_id)
    if record is None or record.status != "calibrated":
        raise MissingCalibration(f"{question_id} has no calibrated threshold")
    if model_version and record.model_version != model_version:
        raise MissingCalibration(f"{question_id} was calibrated for {record.model_version}, not {model_version}")
    return record.threshold
