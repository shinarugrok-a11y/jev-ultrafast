"""The first COMPSD/Beowulf question set. Jev judges; policy still owns authority."""

from .questions import choice_question, noul_question, score_question

EXECUTORS = {
    "deterministic": "Ordinary code can finish this without waking a generative worker.",
    "kimi_explore": "Kimi Code explore: read-only reconnaissance and analysis.",
    "kimi_plan": "Kimi Code plan: architecture and approach with no shell.",
    "kimi_coder": "Kimi Code coder: isolated implementation worker.",
    "cursor": "Cursor free-reign lab: implementation and iteration on an untrusted fork.",
    "pepper": "General Pepper Tusk: VM / GUI / browser computer-use.",
    "grok": "Escalation-level reasoning. Do not wake for small judgments.",
    "codex": "Escalation-level reasoning. Do not wake for small judgments.",
    "human": "A person should take the next step. This is not approval authority.",
    "park": "Hold. Do not wake anyone.",
}

TASK_CLASSES = {
    "information": "Look up or restate known facts.",
    "research": "Investigate an open question.",
    "planning": "Design an approach without executing it.",
    "coding": "Change or write software.",
    "debugging": "Find and explain a defect.",
    "browser": "Interact with a web page.",
    "computer_use": "Interact with a desktop or VM GUI.",
    "relay": "A chat/COMPSD packet that may need a reply or hold.",
    "verification": "Check evidence that work happened.",
    "unknown": "The task shape is not yet clear.",
}

SCORE_LEVELS = ["0 none", "1 very low", "2 low", "3 moderate", "4 high", "5 extreme"]

NOULS = {
    "task.requires_generation.v1": (
        "Does this task require generating new text, code, or a plan?",
        {"true": "A generative worker must compose content.", "false": "A typed choice or ordinary code is enough."},
    ),
    "task.requires_browser.v1": (
        "Does progress require interacting with a web page?",
        {"true": "A browser or computer-use worker is needed.", "false": "No live page interaction is required."},
    ),
    "task.requires_repository_write.v1": (
        "Does the requested outcome require writing to a repository?",
        {"true": "A patch, commit, or branch change is part of the work.", "false": "Read-only analysis is enough."},
    ),
    "task.requires_existing_context.v1": (
        "Does a useful next step require context that is not in this state?",
        {
            "true": "Missing prior packets, files, or session memory block progress.",
            "false": "The current state is enough to start.",
        },
    ),
    "task.requires_visual_verification.v1": (
        "Should a visual/GUI check confirm the outcome?",
        {"true": "Pepper or a browser receipt is the right evidence.", "false": "Tests, files, or logs can prove it."},
    ),
    "task.likely_duplicate_work.v1": (
        "Does this look like work that was already requested or completed?",
        {"true": "A prior packet, branch, or receipt already covers this.", "false": "This appears to be new work."},
    ),
    "agent.should_wake.v1": (
        "Would waking a sleeping worker likely be useful now?",
        {"true": "A specific worker can make progress.", "false": "Stay parked; waking would waste a turn."},
    ),
    "completion.claim_supported.v3": (
        "Does the supplied evidence appear consistent with the claimed outcome?",
        {"true": "The receipts and artifacts match the claim.", "false": "The claim is unsupported or contradicted."},
    ),
    "task.human_review_recommended.v1": (
        "Would a human review of the next step be useful?",
        {
            "true": "Review is recommended because of ambiguity, risk, or missing evidence.",
            "false": "Ordinary policy can continue without extra review.",
        },
    ),
    "relay.needs_reply.v1": (
        "Does this relay packet warrant a reply rather than silence or a hold?",
        {"true": "A reply would be useful.", "false": "No reply should be sent from this judgment."},
    ),
    "task.requires_human.v4": (
        "Does this task need a person's judgment because of skill, ambiguity, or missing context?",
        {
            "true": "A person should look. This is not approval authority.",
            "false": "Automated workers can continue under policy.",
        },
    ),
}


def question_set(ids=None):
    """Build the standardized COMPSD/Beowulf questions, or a subset by id."""
    questions = {
        "routing.best_executor.v2": choice_question(
            EXECUTORS,
            "Which executor should take the next bounded step? This is a recommendation, not authorization.",
        ),
        "routing.task_class.v1": choice_question(
            TASK_CLASSES,
            "What is the primary task class of the current request?",
        ),
        "task.complexity.v1": score_question(SCORE_LEVELS, "How complex is the remaining work?"),
        "task.consequence.v1": score_question(SCORE_LEVELS, "How consequential would a wrong next step be?"),
        "task.context_need.v1": score_question(SCORE_LEVELS, "How much additional context is needed to proceed well?"),
        "repo.change_risk.v2": score_question(SCORE_LEVELS, "How risky are the proposed repository changes?"),
    }
    for question_id, (instructions, criteria) in NOULS.items():
        questions[question_id] = noul_question(instructions, criteria)
    if ids is None:
        return questions
    missing = [i for i in ids if i not in questions]
    if missing:
        raise KeyError(f"Unknown catalog questions: {missing}")
    return {i: questions[i] for i in ids}


COMPSD_QUESTIONS = question_set()
