"""Route recommendations across Beowulf workers. Jev does not dispatch."""

from ..core.catalog import question_set
from .base import ActionSpace, BoundAction, ObservedState

CATALOG_IDS = (
    "routing.best_executor.v2",
    "routing.task_class.v1",
    "task.complexity.v1",
    "task.consequence.v1",
    "task.context_need.v1",
    "task.requires_generation.v1",
    "task.requires_browser.v1",
    "task.requires_repository_write.v1",
    "task.requires_existing_context.v1",
    "task.requires_visual_verification.v1",
    "task.likely_duplicate_work.v1",
    "agent.should_wake.v1",
    "task.human_review_recommended.v1",
    "task.requires_human.v4",
)


class AgentRoutingActionSpace(ActionSpace):
    domain = "routing"
    forbidden = ("dispatch", "wake", "authorize", "declare_done")

    def observe(self, raw_state):
        task = raw_state.get("task", raw_state)
        return ObservedState(
            domain=self.domain,
            goal=task.get("goal") or task.get("text"),
            packet_id=task.get("packet_id"),
            artifacts=task.get("artifacts") or [],
            evidence=task.get("evidence") or [],
            sleeping_agents=task.get("sleeping_agents") or [],
            fingerprint=raw_state.get("fingerprint"),
        )

    def questions(self, observed, *, goal="", history=None, extra=None):
        return question_set(CATALOG_IDS)

    def bind(self, answers, observed):
        executor = answers["routing.best_executor.v2"]["choice"]
        return BoundAction(
            domain=self.domain,
            choice=executor,
            operation="RECOMMEND_ROUTE",
            target=executor,
            task_class=answers["routing.task_class.v1"]["choice"],
            complexity=answers["task.complexity.v1"]["score"],
            consequence=answers["task.consequence.v1"]["score"],
            context_need=answers["task.context_need.v1"]["score"],
            requires_generation=answers["task.requires_generation.v1"]["noul"],
            requires_browser=answers["task.requires_browser.v1"]["noul"],
            requires_repository_write=answers["task.requires_repository_write.v1"]["noul"],
            should_wake=answers["agent.should_wake.v1"]["noul"],
            human_review_recommended=answers["task.human_review_recommended.v1"]["noul"],
            requires_human_judgment=answers["task.requires_human.v4"]["noul"],
            confidence=answers["routing.best_executor.v2"]["confidence"],
            probabilities=answers["routing.best_executor.v2"]["probabilities"],
            kind="recommendation",
        )
