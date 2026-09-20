"""Agent routing reflex: classify a task packet and recommend the first executor. Beowulf policy decides."""

from ..core.questions import STANDARD_QUESTIONS
from .base import ActionSpace, Recommendation

QUESTION_IDS = [
    "task.class.v1",
    "task.complexity.v1",
    "task.consequence.v1",
    "task.context_need.v1",
    "task.requires_generation.v1",
    "task.requires_browser.v1",
    "task.requires_repository_write.v1",
    "task.requires_existing_context.v1",
    "task.requires_visual_verification.v1",
    "task.likely_duplicate_work.v1",
    "task.human_review_recommended.v4",
]


class AgentRoutingActionSpace(ActionSpace):
    domain = "agent_router"

    def __init__(self, packet, available_executors, sleeping_agent=None):
        if not packet.get("goal"):
            raise ValueError("A routing decision needs a goal")
        if not available_executors:
            raise ValueError("Offer at least one executor")
        self.packet = packet
        base = STANDARD_QUESTIONS["routing.best_executor.v2"]
        self.executor_question = base.with_criteria({name: base.criteria.get(name) for name in available_executors})
        self.sleeping_agent = sleeping_agent

    def state(self):
        state = {
            "goal": str(self.packet["goal"])[:4000],
            "source": self.packet.get("source"),
            "context": self.packet.get("context", {}),
            "recent_work": self.packet.get("recent_work", [])[-10:],
            "available_executors": list(self.executor_question.criteria),
        }
        if self.sleeping_agent:
            state["sleeping_agent"] = self.sleeping_agent
        return state

    def questions(self):
        questions = {"routing.best_executor.v2": self.executor_question}
        questions.update({qid: STANDARD_QUESTIONS[qid] for qid in QUESTION_IDS})
        if self.sleeping_agent:
            questions["agent.should_wake.v1"] = STANDARD_QUESTIONS["agent.should_wake.v1"]
        return questions

    def resolve(self, answers):
        executor = answers["routing.best_executor.v2"]
        flags, scores = self.flags_and_scores(self.questions(), answers)
        return Recommendation(
            domain=self.domain,
            operation="ROUTE",
            operation_question="routing.best_executor.v2",
            target=executor["choice"],
            candidate={"executor": executor["choice"], "task_class": answers["task.class.v1"]["choice"]},
            confidence=executor["confidence"],
            probabilities=executor["probabilities"],
            flags=flags,
            scores=scores,
            answers=answers,
        )
