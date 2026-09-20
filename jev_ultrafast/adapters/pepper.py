"""Pepper reflex loop: observe → legal actions → Jev → policy → one approved operation."""

from ..action_spaces.computer import ComputerActionSpace
from ..core.decision import StaleDecision
from ..policy.authority import approval_required


class PepperLoop:
    """Hands and eyes. Jev picks where/what; Kimi writes text; Beowulf says whether."""

    def __init__(self, gateway, executor, *, kimi=None):
        self.gateway = gateway
        self.executor = executor
        self.kimi = kimi
        self.space = ComputerActionSpace()

    def step(self, observation, goal, *, action_kind=None):
        if approval_required(action_kind):
            return {"status": "human_required", "executed": False, "reason": "HUMAN REQUIRED"}
        observed = self.space.observe(observation)
        decision = self.gateway.decide(observation, policy_context={"domain": "computer", "goal": goal})
        bound = decision["bound"]
        if bound["operation"] in {"BLOCKED", "REQUEST_HELP"}:
            return {
                "status": bound["operation"].lower(),
                "executed": False,
                "decision_id": decision["decision_id"],
                "bound": bound,
            }
        try:
            action = {"operation": bound["operation"], "target": bound["target"]}
            self.gateway.consume(decision["decision_id"], dict(observed), action)
        except StaleDecision:
            return {"status": "stale", "executed": False, "decision_id": decision["decision_id"]}
        text = None
        if bound.get("wake_kimi"):
            if self.kimi is None:
                raise ValueError("TYPE_TEXT needs Kimi; Pepper will not invent the string.")
            job = self.kimi.run_job("plan", f"Compose the exact text for {bound['choice']} given goal: {goal}")
            text = job["result"]
        result = self.executor.execute_once(bound, text=text)
        receipt = {"kind": "visual", "result": result, "operation": bound["operation"]}
        self.gateway.receipt(decision["decision_id"], receipt)
        return {
            "status": "executed",
            "executed": True,
            "decision_id": decision["decision_id"],
            "bound": bound,
            "receipt": receipt,
            "text": text,
        }
