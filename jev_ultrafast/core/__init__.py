"""Shared reflex core: typed decisions, validation, calibration, action spaces."""

from .action_space import ActionSpace
from .calibration import CALIBRATED_QUESTIONS, CalibrationRecord, QuestionSpec, get_spec, is_calibrated
from .decision import Decision, consume_once, state_hash
from .validation import validate_choice

__all__ = [
    "ActionSpace",
    "CALIBRATED_QUESTIONS",
    "CalibrationRecord",
    "Decision",
    "QuestionSpec",
    "consume_once",
    "get_spec",
    "is_calibrated",
    "state_hash",
    "validate_choice",
]
