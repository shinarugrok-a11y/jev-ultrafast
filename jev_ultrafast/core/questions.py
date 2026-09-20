"""Typed System One questions. IDs belong to code; instructions are the judgment."""


def choice_question(criteria, instructions):
    if not isinstance(criteria, dict) or not criteria:
        raise ValueError("Choice questions need a non-empty criteria map")
    if len(criteria) > 255:
        raise ValueError("Choice cardinality is capped at 255; use hierarchical_choice")
    return {"type": "choice", "criteria": criteria, "instructions": instructions}


def score_question(criteria, instructions):
    if not isinstance(criteria, (list, tuple)) or len(criteria) < 2:
        raise ValueError("Score questions need at least two ordered levels")
    if len(criteria) > 10:
        raise ValueError("Score questions accept at most 10 levels")
    return {"type": "score", "criteria": list(criteria), "instructions": instructions}


def noul_question(instructions, criteria=None):
    question = {"type": "noul", "instructions": instructions}
    if criteria is not None:
        if set(criteria) - {"true", "false"}:
            raise ValueError("Noul criteria may only describe true and false")
        question["criteria"] = criteria
    return question


def as_wire(questions):
    """Normalize a list or map of questions into a TypeSafe questions map."""
    if isinstance(questions, dict):
        items = questions.items()
    else:
        items = []
        for entry in questions:
            if not isinstance(entry, dict) or "id" not in entry:
                raise ValueError("Question lists must include an id on each entry")
            items.append((entry["id"], {k: v for k, v in entry.items() if k != "id"}))
    wire = {}
    for question_id, body in items:
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("Every question needs a non-empty id")
        if not isinstance(body, dict) or body.get("type") not in {"choice", "score", "noul"}:
            raise ValueError(f"Question {question_id!r} must declare type choice, score, or noul")
        kind = body["type"]
        if kind == "choice":
            wire[question_id] = choice_question(body["criteria"], body.get("instructions"))
        elif kind == "score":
            wire[question_id] = score_question(body["criteria"], body.get("instructions"))
        else:
            wire[question_id] = noul_question(body.get("instructions"), body.get("criteria"))
    return wire
