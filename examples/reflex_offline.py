"""Offline reflex routing: uv run python examples/reflex_offline.py"""

from jev_ultrafast import BeowulfOrchestrator, SystemOneGateway
from jev_ultrafast.action_spaces import AgentRoutingActionSpace
from jev_ultrafast.providers.base import ScriptedProvider

GOAL = "The Chrono Maps world selector is broken. Figure out the problem, fix it, and show me it works."


def answers(_state, questions):
    space = AgentRoutingActionSpace()
    asked = questions or space.questions({"goal": GOAL})
    out = {}
    for qid, question in asked.items():
        if question["type"] == "choice":
            if "executor" in qid:
                pick = "kimi_explore"
            elif "task_class" in qid:
                pick = "debugging"
            else:
                pick = next(iter(question["criteria"]))
            if pick not in question["criteria"]:
                pick = next(iter(question["criteria"]))
            out[qid] = {
                "choice": pick,
                "confidence": 0.8,
                "probabilities": {key: float(key == pick) for key in question["criteria"]},
            }
        elif question["type"] == "score":
            out[qid] = {
                "score": 2,
                "legend": {str(i): level for i, level in enumerate(question["criteria"])},
                "probabilities": {str(i): float(i == 2) for i in range(len(question["criteria"]))},
                "confidence": 0.7,
            }
        else:
            high_ids = {
                "task.requires_repository_write.v1",
                "task.requires_visual_verification.v1",
                "agent.should_wake.v1",
            }
            high = qid in high_ids
            out[qid] = {"noul": 0.94 if high else 0.12}
    return out


def main():
    orchestrator = BeowulfOrchestrator(SystemOneGateway(ScriptedProvider(answers, model_version="jev-latest")))
    route = orchestrator.consider({"goal": GOAL})
    print(route["executor"], route["task_class"], route["decision_id"])
    print("kind=", route["kind"], "human_required=", route["human_required"])


if __name__ == "__main__":
    main()
