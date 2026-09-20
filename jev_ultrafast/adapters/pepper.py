"""General Pepper Tusk's reflex loop.

Pepper observes the screen. The normalizer builds legal actions. Jev picks one. Beowulf policy says whether it
may happen. Pepper executes exactly one approved operation, produces a state receipt, and the loop repeats.
If actual text must be composed, the loop returns ``wake_kimi`` instead of typing anything.

Jev = where / what.  Kimi = what to say.  Pepper = physically do it.  Beowulf = whether it is allowed.
"""

from dataclasses import asdict, dataclass, field

from ..action_spaces.computer import ComputerActionSpace
from ..core.decision import state_hash


@dataclass
class StepResult:
    status: str  # executed | wake_kimi | wait | request_help | blocked | claimed_done | held
    decision_id: str
    operation: str
    verdict: str
    requested_action: dict | None = None
    receipt: dict | None = None
    reasons: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class PepperLoop:
    def __init__(self, gateway, executor, wake_threshold_question="task.requires_generation.v1"):
        self.gateway = gateway
        self.executor = executor
        self.wake_question = wake_threshold_question

    def step(self, observation, goal, history=(), categories=()):
        request = {
            "domain": "computer",
            "input": {"observation": observation, "goal": goal, "history": list(history)},
            "policy_context": {"categories": list(categories)},
        }
        response = self.gateway.decide(request)
        recommendation, verdict = response["recommendation"], response["policy"]["verdict"]
        operation = recommendation["operation"]
        result = StepResult("held", response["decision_id"], operation, verdict, reasons=response["policy"]["reasons"])
        if verdict != "act":
            return result
        if operation in {"REQUEST_HELP", "BLOCKED"}:
            result.status = operation.lower()
            return result
        if operation == "DONE":
            result.status = "claimed_done"  # A claim. Verification and receipts decide whether it is true.
            return result
        candidate = recommendation["candidate"]
        requested = {"operation": operation, "element_id": None, "bounds": None}
        if candidate:
            requested.update(element_id=candidate["element_id"], bounds=candidate["bounds"], label=candidate["label"])
        if operation == "TYPE":
            # Text is never produced here. Hand the field to the generation layer with the same state hash.
            result.status = "wake_kimi"
            result.requested_action = {**requested, "state_hash": response["state_hash"]}
            return result
        # Consume before executing. A retry after this line cannot execute twice.
        state = self._state_for(observation, goal, history)
        self.gateway.consume(response["decision_id"], state, requested)
        receipt = {"kind": "file", "executed": requested, "before": response["state_hash"]}
        try:
            receipt["result"] = self.executor(requested)
        finally:
            # Execution is recorded before the next observation, even if the executor raised after acting.
            self.gateway.result(response["decision_id"], receipt)
        result.status = "wait" if operation == "WAIT" else "executed"
        result.requested_action = requested
        result.receipt = receipt
        return result

    @staticmethod
    def _state_for(observation, goal, history):
        return ComputerActionSpace(observation, goal, history).state()

    @staticmethod
    def changed(before, observation, goal, history=()):
        return state_hash(ComputerActionSpace(observation, goal, history).state()) != before
