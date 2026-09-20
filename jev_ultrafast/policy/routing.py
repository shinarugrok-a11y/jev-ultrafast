"""Turn Jev recommendations into a route using per-question locks, not a global cutoff."""

from ..core.calibration import apply_lock, load_lock
from .authority import HUMAN_REQUIRED, approval_required, jev_must_not


def route_recommendation(bound, answers, *, action_kind=None, locks=None, model_version=None):
    """Compose catalog answers in code. Never treat Jev as authorization or DONE."""
    if action_kind and jev_must_not(action_kind):
        return {
            "executor": "park",
            "allowed": False,
            "reason": "jev_forbidden_action",
            "human_required": False,
            "jev_vote": None,
        }
    if action_kind and approval_required(action_kind):
        return {
            "executor": "human",
            "allowed": False,
            "reason": "HUMAN REQUIRED",
            "human_required": True,
            "category": action_kind,
            "jev_vote": None,
        }
    executor_answer = answers.get("routing.best_executor.v2") or {
        "choice": bound.get("choice"),
        "probabilities": bound.get("probabilities") or {},
        "confidence": bound.get("confidence", 0),
    }
    lock = (locks or {}).get("routing.best_executor.v2")
    if lock is None:
        try:
            lock = load_lock("routing.best_executor.v2")
        except FileNotFoundError:
            lock = None
    gated = None
    if lock is not None:
        gated = apply_lock(lock, executor_answer, model_version=model_version)
        executor = executor_answer["choice"] if gated["accepted"] else gated["fallback"] or "park"
    else:
        executor = executor_answer["choice"]
    wake = answers.get("agent.should_wake.v1", {}).get("noul")
    if wake is not None:
        wake_lock = (locks or {}).get("agent.should_wake.v1")
        if wake_lock is None:
            try:
                wake_lock = load_lock("agent.should_wake.v1")
            except FileNotFoundError:
                wake_lock = None
        if wake_lock is not None:
            wake_gate = apply_lock(wake_lock, answers["agent.should_wake.v1"], model_version=model_version)
            if not wake_gate["accepted"] and executor not in {"deterministic", "park", "human"}:
                executor = "park"
                gated = {**(gated or {}), "wake_blocked": True}
    return {
        "executor": executor,
        "allowed": executor not in {"human", "park"},
        "reason": "recommendation",
        "human_required": False,
        "human_review_recommended": answers.get("task.human_review_recommended.v1", {}).get("noul"),
        "task_class": bound.get("task_class") or answers.get("routing.task_class.v1", {}).get("choice"),
        "gate": gated,
        "jev_vote": "ignored" if action_kind in HUMAN_REQUIRED else "advisory",
        "kind": "recommendation",
    }
