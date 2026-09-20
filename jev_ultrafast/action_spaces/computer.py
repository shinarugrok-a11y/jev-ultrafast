"""Computer/GUI action space for Pepper. Jev chooses where/what; Pepper executes once."""

from ..core.questions import choice_question
from .base import ActionSpace, BoundAction, ObservedState

OPERATIONS = {
    "CLICK": "Click an observed control.",
    "TYPE_TEXT": "Type into an observed field. Kimi supplies the string when generation is required.",
    "WAIT": "Wait briefly for the UI to settle. Not evidence of loading by itself.",
    "REQUEST_HELP": "The next step needs a generative or human worker.",
    "BLOCKED": "No supported operation can progress.",
}


class ComputerActionSpace(ActionSpace):
    domain = "computer"
    forbidden = ("shell", "credential", "sudo")

    def observe(self, raw_state):
        controls = raw_state.get("controls") or raw_state.get("actions") or []
        indexed = []
        click_targets = {}
        type_targets = {}
        for i, control in enumerate(controls, start=1):
            index = str(control.get("index") or i)
            item = {
                "index": index,
                "id": control.get("id", f"c{index}"),
                "role": control.get("role", "unknown"),
                "label": control.get("label", ""),
                "value": control.get("value", ""),
                "operations": list(control.get("operations") or ["CLICK"]),
            }
            indexed.append(item)
            if "CLICK" in item["operations"]:
                click_targets[index] = item
            if "TYPE_TEXT" in item["operations"]:
                type_targets[index] = item
        return ObservedState(
            domain=self.domain,
            title=raw_state.get("title"),
            app=raw_state.get("app"),
            elements=indexed,
            click_targets=click_targets,
            type_targets=type_targets,
            fingerprint=raw_state.get("fingerprint"),
        )

    def questions(self, observed, *, goal="", history=None, extra=None):
        questions = {
            "operation": choice_question(
                OPERATIONS, {"goal": goal, "question": "Which one computer operation should Pepper consider?"}
            ),
        }
        if observed["click_targets"]:
            questions["click_target"] = choice_question(
                {i: f"[{i}] {item['label']}" for i, item in observed["click_targets"].items()},
                {"goal": goal, "operation": "CLICK"},
            )
        if observed["type_targets"]:
            questions["type_text_target"] = choice_question(
                {i: f"[{i}] {item['label']}" for i, item in observed["type_targets"].items()},
                {"goal": goal, "operation": "TYPE_TEXT"},
            )
        return questions

    def bind(self, answers, observed):
        operation = answers["operation"]["choice"]
        target = None
        choice = operation
        probabilities = {operation: answers["operation"]["probabilities"][operation]}
        if operation == "CLICK" and "click_target" in answers:
            target = answers["click_target"]["choice"]
            choice = observed["click_targets"][target]["id"]
            probabilities = {
                item["id"]: answers["click_target"]["probabilities"][index]
                for index, item in observed["click_targets"].items()
            }
        elif operation == "TYPE_TEXT" and "type_text_target" in answers:
            target = answers["type_text_target"]["choice"]
            choice = observed["type_targets"][target]["id"]
            probabilities = {
                item["id"]: answers["type_text_target"]["probabilities"][index]
                for index, item in observed["type_targets"].items()
            }
        return BoundAction(
            domain=self.domain,
            choice=choice,
            operation=operation,
            target=target,
            wake_kimi=operation == "TYPE_TEXT",
            confidence=answers["operation"]["confidence"],
            probabilities=probabilities,
            operation_probabilities=answers["operation"]["probabilities"],
            kind="recommendation",
        )
