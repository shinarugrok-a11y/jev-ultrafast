"""Reject any answer the code cannot safely branch on. Nothing executes on an invalid response."""

import math

INVALID = "Invalid TypeSafe response; no action executed."


def _unit(number):
    return type(number) in (int, float) and math.isfinite(number) and 0 <= number <= 1


def _distribution(probabilities, keys):
    return (
        isinstance(probabilities, dict)
        and set(probabilities) == set(keys)
        and all(_unit(p) for p in probabilities.values())
        and abs(sum(probabilities.values()) - 1) < 0.02
    )


def validate_choice(answer, ids):
    try:
        probabilities = answer["probabilities"]
        valid = (
            answer["choice"] in ids
            and _distribution(probabilities, ids)
            and _unit(answer["confidence"])
            and probabilities[answer["choice"]] >= max(probabilities.values()) - 1e-6
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError(INVALID)
    return answer


def validate_score(answer, levels):
    keys = [str(i) for i in range(len(levels))]
    try:
        score = answer["score"]
        valid = (
            type(score) in (int, float)
            and math.isfinite(score)
            and 0 <= score <= len(levels) - 1
            and _distribution(answer["probabilities"], keys)
            and _unit(answer["confidence"])
        )
        if valid:
            expected = sum(int(k) * p for k, p in answer["probabilities"].items())
            valid = abs(expected - score) < 0.05
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError(INVALID)
    return answer


def validate_noul(answer):
    try:
        valid = _unit(answer["noul"])
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise ValueError(INVALID)
    return answer


def validate_answers(questions, answers):
    """Validate every asked question by its declared type. Extra answers are ignored, missing ones are errors."""
    if not isinstance(answers, dict):
        raise ValueError(INVALID)
    validated = {}
    for key, q in questions.items():
        answer = answers.get(key)
        if q.type == "choice":
            validated[key] = validate_choice(answer, q.criteria)
        elif q.type == "score":
            validated[key] = validate_score(answer, q.criteria)
        else:
            validated[key] = validate_noul(answer)
    return validated
