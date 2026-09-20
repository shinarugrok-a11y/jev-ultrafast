"""Reject malformed System One answers before any caller can act on them."""

import math


def _finite_unit(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def validate_choice(answer, ids, *, error="Invalid System One choice; no action executed."):
    try:
        probabilities = answer["probabilities"]
        numbers = [*probabilities.values(), answer["confidence"]]
        valid = (
            answer["choice"] in ids
            and set(probabilities) == set(ids)
            and all(_finite_unit(n) for n in numbers)
            and abs(sum(probabilities.values()) - 1) < 0.02
            and probabilities[answer["choice"]] >= max(probabilities.values()) - 1e-6
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError(error)
    return answer


def validate_score(answer, levels, *, error="Invalid System One score; no action executed."):
    ids = {str(i) for i in range(len(levels))}
    try:
        probabilities = answer["probabilities"]
        numbers = [*probabilities.values(), answer["confidence"]]
        score = answer["score"]
        valid = (
            type(score) in (int, float)
            and math.isfinite(score)
            and 0 <= score <= len(levels) - 1
            and set(probabilities) == ids
            and all(_finite_unit(n) for n in numbers)
            and abs(sum(probabilities.values()) - 1) < 0.02
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError(error)
    return answer


def validate_noul(answer, *, error="Invalid System One noul; no action executed."):
    try:
        value = answer["noul"]
        valid = _finite_unit(value)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError(error)
    return answer


def validate_answers(questions, answers, *, error="Invalid System One response; no action executed."):
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError(error)
    validated = {}
    for question_id, question in questions.items():
        answer = answers[question_id]
        kind = question["type"]
        if kind == "choice":
            validated[question_id] = validate_choice(answer, question["criteria"], error=error)
        elif kind == "score":
            validated[question_id] = validate_score(answer, question["criteria"], error=error)
        elif kind == "noul":
            validated[question_id] = validate_noul(answer, error=error)
        else:
            raise ValueError(error)
    return validated


def distributions(answers):
    out = {}
    for question_id, answer in answers.items():
        if "probabilities" in answer:
            out[question_id] = dict(answer["probabilities"])
        elif "noul" in answer:
            out[question_id] = {"true": answer["noul"], "false": 1 - answer["noul"]}
    return out


def confidences(answers):
    return {qid: answer.get("confidence") for qid, answer in answers.items() if "confidence" in answer}
