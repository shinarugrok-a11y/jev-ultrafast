"""Hierarchical Choice when a flat option set is too large for one question."""

from .questions import choice_question

MAX_FLAT = 32


def hierarchical_choice(options, *, instructions, group_size=16, parent_id="group"):
    """Split a large option map into a parent group Choice plus per-group heads.

    Speculative fan-out: ask the parent and every group in one request. Code
    consumes only the selected group's head. Application code still executes.
    """
    if not options:
        raise ValueError("hierarchical_choice needs options")
    keys = list(options)
    questions = {}
    groups = {}
    if len(keys) <= MAX_FLAT:
        questions[parent_id] = choice_question(options, instructions)
        return {"parent_id": parent_id, "questions": questions, "groups": groups, "flat": True}
    parent = {}
    for offset in range(0, len(keys), group_size):
        chunk = keys[offset : offset + group_size]
        name = f"group_{offset // group_size + 1}"
        parent[name] = f"Options {chunk[0]} … {chunk[-1]}"
        groups[name] = {k: options[k] for k in chunk}
        questions[name] = choice_question(groups[name], {"assume_group": name, "question": instructions})
    questions[parent_id] = choice_question(parent, {"question": instructions, "role": "select_group"})
    return {"parent_id": parent_id, "questions": questions, "groups": groups, "flat": False}


def bind_hierarchy(tree, answers):
    """Consume only the selected group's target. Unused heads cannot execute."""
    parent_id = tree["parent_id"]
    if tree["flat"]:
        answer = answers[parent_id]
        return {"group": None, "choice": answer["choice"], "probabilities": answer["probabilities"]}
    group_name = answers[parent_id]["choice"]
    if group_name not in tree["groups"]:
        raise ValueError("Parent choice is not an offered group")
    child = answers[group_name]
    return {"group": group_name, "choice": child["choice"], "probabilities": child["probabilities"]}
