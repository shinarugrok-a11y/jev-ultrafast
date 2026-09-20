"""Computer domain. One approved operation over observed elements.

Pepper observes screen/state, the normalizer builds legal actions, Jev picks
where/what, Beowulf policy gates execution, Pepper performs exactly one step,
then a visual/state receipt closes the loop. Text composition wakes Kimi.
"""

from jev_ultrafast.core.action_space import ActionSpace, LegalAction

OPERATIONS = ("CLICK", "TYPE", "WAIT", "REQUEST_HELP", "BLOCKED")


class ComputerActionSpace(ActionSpace):
    name = "computer"
    operations = OPERATIONS

    def legal_actions(self, state):
        elements = state.get("elements", [])
        legal = [
            LegalAction(id="wait", operation="WAIT", target=None, label="Wait for useful state"),
            LegalAction(id="request_help", operation="REQUEST_HELP", target=None, label="Request help"),
            LegalAction(id="blocked", operation="BLOCKED", target=None, label="Blocked"),
        ]
        for element in elements:
            eid = element.get("id", "?")
            for operation in ("CLICK", "TYPE"):
                legal.append(
                    LegalAction(
                        id=f"{operation.lower()}:{eid}",
                        operation=operation,
                        target=eid,
                        label=f"{operation} {element.get('label', eid)}",
                    )
                )
        return legal
