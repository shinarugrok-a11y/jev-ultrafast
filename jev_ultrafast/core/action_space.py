"""Universal ActionSpace. One observation snapshot, bounded legal actions.

The browser domain keeps its dynamic operation + compatible-target shape:
one TypeSafe request, operation and target heads in parallel, consume only the
selected operation's target. Relay, router, repository, and computer domains
reuse the same consume-once, fingerprint-bound contract with their own legal
actions. The model never emits selectors or executable code.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LegalAction:
    id: str
    operation: str
    target: str | None
    label: str
    detail: dict = field(default_factory=dict, compare=False)


class ActionSpace:
    name = "base"
    operations: tuple = ()

    def legal_actions(self, state):
        raise NotImplementedError

    def fingerprint(self, state):
        from .decision import state_hash

        return state_hash(state)

    def check_target(self, operation, target, state):
        offered = {a.id: a for a in self.legal_actions(state) if a.operation == operation}
        if target not in offered:
            raise ValueError(f"Target {target!r} is not a legal {operation} target in {self.name}.")
        return offered[target]
