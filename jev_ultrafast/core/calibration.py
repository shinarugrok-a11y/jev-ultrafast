"""Calibration-first question registry. No magical global confidence threshold.

Every important question has an ID and a checked-in calibration record:
labeled fixtures, metric, chosen threshold, model version, policy version.
Code owns thresholds; Jev returns distributions and confidence only.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class QuestionSpec:
    id: str
    kind: str  # "choice" | "noul" | "score"
    description: str
    options: tuple = ()
    scale: tuple = ()
    threshold: float | None = None
    policy_version: str = "policy-v1"
    model_version: str = "jev-latest"


@dataclass(frozen=True)
class CalibrationRecord:
    question_id: str
    model_version: str
    policy_version: str
    fixtures: int
    metric: str
    metric_value: float
    threshold: float | None
    status: str = "provisional"  # "provisional" | "locked"


EXECUTORS = (
    "deterministic",
    "kimi_explore",
    "kimi_plan",
    "kimi_coder",
    "cursor",
    "pepper",
    "grok",
    "codex",
    "human",
    "park",
)

TASK_CLASSES = (
    "information",
    "research",
    "planning",
    "coding",
    "debugging",
    "browser",
    "computer_use",
    "relay",
    "verification",
    "unknown",
)

CALIBRATED_QUESTIONS: dict[str, QuestionSpec] = {
    "routing.best_executor.v2": QuestionSpec(
        id="routing.best_executor.v2",
        kind="choice",
        description="Which executor should handle this task first.",
        options=EXECUTORS,
    ),
    "task.class.v1": QuestionSpec(
        id="task.class.v1",
        kind="choice",
        description="What shape is this task.",
        options=TASK_CLASSES,
    ),
    "task.complexity.v1": QuestionSpec(
        id="task.complexity.v1", kind="score", description="Complexity 0-5.", scale=(0, 5)
    ),
    "task.consequence.v1": QuestionSpec(
        id="task.consequence.v1", kind="score", description="Consequence 0-5.", scale=(0, 5)
    ),
    "task.context_need.v1": QuestionSpec(
        id="task.context_need.v1", kind="score", description="Existing-context need 0-5.", scale=(0, 5)
    ),
    "task.requires_generation.v1": QuestionSpec(
        id="task.requires_generation.v1", kind="noul", description="Generation-shaped work fits an LLM.",
    ),
    "task.requires_browser.v1": QuestionSpec(
        id="task.requires_browser.v1", kind="noul", description="Needs browser observation.",
    ),
    "task.requires_repository_write.v1": QuestionSpec(
        id="task.requires_repository_write.v1", kind="noul", description="Needs repo writes.",
    ),
    "task.requires_existing_context.v1": QuestionSpec(
        id="task.requires_existing_context.v1", kind="noul", description="Needs existing context.",
    ),
    "task.requires_visual_verification.v1": QuestionSpec(
        id="task.requires_visual_verification.v1", kind="noul", description="Needs visual verification.",
    ),
    "task.likely_duplicate_work.v1": QuestionSpec(
        id="task.likely_duplicate_work.v1", kind="noul", description="Duplicates known work.",
    ),
    "agent.should_wake.v1": QuestionSpec(
        id="agent.should_wake.v1",
        kind="noul",
        description="Waking a sleeping agent is useful now.",
        threshold=0.7,
    ),
    "relay.needs_reply.v1": QuestionSpec(
        id="relay.needs_reply.v1",
        kind="noul",
        description="This relay packet needs a reply.",
        threshold=0.6,
    ),
    "task.human_review_recommended.v4": QuestionSpec(
        id="task.human_review_recommended.v4",
        kind="noul",
        description="Human review recommended. Whether approval is required is deterministic policy, not a Jev vote.",
        threshold=0.5,
    ),
    "repo.change_risk.v2": QuestionSpec(
        id="repo.change_risk.v2", kind="score", description="Change risk 0-5.", scale=(0, 5)
    ),
    "completion.claim_supported.v3": QuestionSpec(
        id="completion.claim_supported.v3",
        kind="noul",
        description="Evidence appears consistent with the claimed outcome. Cannot set DONE.",
        threshold=0.8,
    ),
}

CALIBRATION_RECORDS: dict[str, CalibrationRecord] = {
    qid: CalibrationRecord(
        question_id=qid,
        model_version="jev-latest",
        policy_version="policy-v1",
        fixtures=0,
        metric="brier",
        metric_value=1.0,
        threshold=spec.threshold,
        status="provisional",
    )
    for qid, spec in CALIBRATED_QUESTIONS.items()
}


def get_spec(question_id):
    try:
        return CALIBRATED_QUESTIONS[question_id]
    except KeyError:
        raise ValueError(f"Unknown question {question_id!r}") from None


def is_calibrated(question_id):
    return CALIBRATED_QUESTIONS[question_id].threshold is not None if question_id in CALIBRATED_QUESTIONS else False


def apply_threshold(question_id, probability):
    """Code-owned threshold check. Raises when the question has no locked threshold."""
    spec = get_spec(question_id)
    if spec.kind != "noul" or spec.threshold is None:
        raise ValueError(f"No calibrated threshold for {question_id}; do not invent one.")
    return bool(probability >= spec.threshold)
