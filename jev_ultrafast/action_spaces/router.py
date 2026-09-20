"""Agent-routing domain. Recommends an executor; policy decides and dispatches."""

from jev_ultrafast.core.action_space import ActionSpace, LegalAction
from jev_ultrafast.core.calibration import EXECUTORS


class AgentRoutingActionSpace(ActionSpace):
    name = "agent_router"
    operations = ("RECOMMEND_EXECUTOR",)

    def legal_actions(self, state):
        task = state.get("task", "task")
        return [
            LegalAction(
                id=f"executor:{name}",
                operation="RECOMMEND_EXECUTOR",
                target=name,
                label=f"Recommend {name} for {task}",
            )
            for name in EXECUTORS
        ]
