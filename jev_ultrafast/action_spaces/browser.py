"""Browser action space: operation + compatible DOM targets. Execution stays in Browser."""

from ..core.questions import choice_question
from ..questions import NEXT_ACTION, TARGET
from .base import ActionSpace, BoundAction, ObservedState

OPERATIONS = {"click": "CLICK", "fill": "TYPE_TEXT", "select": "SELECT"}
OPERATION_LABELS = {
    "CLICK": "Click an element, button, menu option, autocomplete suggestion, or calendar day.",
    "TYPE_TEXT": "Enter or replace text in an editable field. A small LLM will supply the value from the goal.",
    "SELECT": "Select an observed dropdown value.",
}


def index_actions(actions):
    """One index per observed element; each operation has its own valid target choices."""
    elements, indices, targets, controls = [], {}, {}, {}
    for action in actions:
        kind = action["kind"]
        if kind not in OPERATIONS:
            controls[action["id"].upper()] = action
            continue
        node = action["node"]
        if node not in indices:
            index = str(len(elements) + 1)
            indices[node] = index
            element = {k: action[k] for k in ("role", "value", "checked", "selected", "expanded") if k in action}
            element.update(index=index, label=action["label"].split(" → ")[0], operations=[])
            if kind == "select":
                element["value"] = action.get("current_value", "")
                element["options"] = []
            elements.append(element)
        index = indices[node]
        operation = OPERATIONS[kind]
        group = targets.setdefault(operation, {})
        element = elements[int(index) - 1]
        if operation not in element["operations"]:
            element["operations"].append(operation)
        target = index
        if kind == "select":
            target = f"{index}:{len(element['options']) + 1}"
            element["options"].append({"index": target, "label": action["label"], "value": action["value"]})
        group[target] = action
    return elements, targets, controls


class BrowserActionSpace(ActionSpace):
    domain = "browser"

    def observe(self, raw_state):
        actions = raw_state["actions"] if isinstance(raw_state, dict) and "actions" in raw_state else raw_state
        elements, targets, controls = index_actions(actions)
        page = raw_state if isinstance(raw_state, dict) else {}
        observed = ObservedState(
            domain=self.domain,
            url=page.get("url"),
            title=page.get("title"),
            text=page.get("text"),
            elements=elements,
            targets=targets,
            controls=controls,
            actions=actions,
            fingerprint=page.get("fingerprint"),
        )
        return observed

    def questions(self, observed, *, goal="", history=None, extra=None):
        history = history or []
        operations = {key: OPERATION_LABELS[key] for key in observed["targets"]}
        operations.update({key: value["label"] for key, value in observed["controls"].items()})
        operations.update(
            DONE="Every requirement is visibly satisfied.",
            BLOCKED="No supported operation can progress.",
        )
        questions = {
            "operation": choice_question(operations, {"goal": goal, "rules": NEXT_ACTION}),
        }
        for operation, candidates in observed["targets"].items():
            questions[operation.lower() + "_target"] = choice_question(
                {
                    index: {
                        "element": f"[{index}] {action['label']}",
                        "current_value": action.get("current_value", action.get("value", "")),
                        **{k: action[k] for k in ("role", "checked", "selected", "expanded") if k in action},
                    }
                    for index, action in candidates.items()
                },
                {"goal": goal, "operation": operation, "rules": [NEXT_ACTION, TARGET]},
            )
        return questions

    def bind(self, answers, observed):
        operation = answers["operation"]["choice"]
        targets = observed["targets"]
        controls = observed["controls"]
        target = None
        target_answer = None
        probabilities = {}
        if operation in targets:
            key = operation.lower() + "_target"
            target_answer = answers[key]
            target = target_answer["choice"]
            choice = targets[operation][target]["id"]
            probabilities = {
                action["id"]: target_answer["probabilities"][index] for index, action in targets[operation].items()
            }
        else:
            choice = controls[operation]["id"] if operation in controls else operation
            probabilities[choice] = answers["operation"]["probabilities"][operation]
        return BoundAction(
            domain=self.domain,
            choice=choice,
            operation=operation,
            target=target,
            probabilities=probabilities,
            confidence=answers["operation"]["confidence"],
            operation_probabilities=answers["operation"]["probabilities"],
            target_probabilities=target_answer["probabilities"] if target_answer else {},
            target_confidence=target_answer["confidence"] if target_answer else None,
            kind="recommendation",
        )

    def provider_state(self, observed, goal, history):
        return {
            "page": {k: observed[k] for k in ("url", "title", "text")},
            "elements": observed["elements"],
            "recent_actions": [
                {k: h.get(k) for k in ("action", "kind", "text", "page_changed")} for h in (history or [])[-10:]
            ],
            "goal": goal,
        }
