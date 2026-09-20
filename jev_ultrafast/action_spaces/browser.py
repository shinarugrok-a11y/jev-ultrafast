"""Browser domain. Preserves the dynamic operation + compatible-target shape.

One node receives one index even when it supports click and type. Each
operation head offers only compatible targets; the executor consumes only the
selected operation's target. Model output never becomes selectors or code.
"""

from jev_ultrafast.core.action_space import ActionSpace, LegalAction


class BrowserActionSpace(ActionSpace):
    name = "browser"
    operations = ("CLICK", "TYPE_TEXT", "SELECT", "SCROLL_UP", "SCROLL_DOWN", "WAIT", "DONE", "BLOCKED")

    def legal_actions(self, state):
        from jev_ultrafast.model import action_space

        _elements, targets, controls = action_space(state["actions"])
        legal = []
        for operation, candidates in targets.items():
            for index in candidates:
                legal.append(
                    LegalAction(
                        id=candidates[index]["id"],
                        operation=operation,
                        target=index,
                        label=candidates[index]["label"],
                    )
                )
        for key, control in controls.items():
            legal.append(LegalAction(id=control["id"], operation=key, target=None, label=control["label"]))
        for terminal in ("DONE", "BLOCKED"):
            legal.append(LegalAction(id=terminal, operation=terminal, target=None, label=terminal))
        return legal
