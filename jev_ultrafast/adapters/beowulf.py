"""Beowulf-facing orchestrator: normalize, ask Jev, apply policy, never execute Jev's vote."""

from ..action_spaces import AgentRoutingActionSpace
from ..core.calibration import load_lock
from ..evidence.completion import verify_completion
from ..policy.authority import approval_required
from ..policy.routing import route_recommendation
from .kimi_acp import KIMI_WORKERS


class BeowulfOrchestrator:
    """Dispatcher. Jev judges; this object routes and reconciles receipts."""

    def __init__(self, gateway, *, kimi=None, pepper=None):
        self.gateway = gateway
        self.kimi = kimi
        self.pepper = pepper
        self.space = AgentRoutingActionSpace()

    def consider(self, task, *, action_kind=None, history=None):
        if approval_required(action_kind):
            return {
                "executor": "human",
                "allowed": False,
                "reason": "HUMAN REQUIRED",
                "human_required": True,
                "category": action_kind,
                "jev_vote": None,
                "kind": "policy",
            }
        decision = self.gateway.decide(
            task, policy_context={"domain": "routing", "goal": task.get("goal", "")}, history=history
        )
        route = route_recommendation(
            decision["bound"],
            decision["answers"],
            action_kind=action_kind,
            model_version=decision["model_version"],
        )
        return {
            **route,
            "decision_id": decision["decision_id"],
            "state_hash": decision["state_hash"],
            "bound": decision["bound"],
        }

    def dispatch_kimi(self, route, prompt, *, cwd="."):
        worker = route.get("executor")
        if worker not in KIMI_WORKERS:
            raise ValueError("Route is not a Kimi worker")
        if self.kimi is None:
            raise ValueError("No Kimi ACP client configured")
        return self.kimi.run_job(KIMI_WORKERS[worker]["agent"], prompt, cwd=cwd)

    def close_task(self, claim, receipts, answers=None, *, action_kind=None):
        return verify_completion(
            claim, receipts, answers, action_kind=action_kind, lock=load_lock("completion.claim_supported.v3")
        )
