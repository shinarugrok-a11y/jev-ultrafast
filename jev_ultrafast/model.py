"""TypeSafe makes choices; an optional small OpenAI-compatible model writes field values."""

import json
import os
import time

from .action_spaces.browser import BrowserActionSpace, index_actions
from .core.validation import validate_choice as _validate_choice
from .providers.typesafe import post_json
from .questions import TEXT_VALUE


def validate_choice(answer, ids):
    return _validate_choice(answer, ids, error="Invalid TypeSafe response; no action executed.")


def action_space(actions):
    """One index per observed element; each operation has its own valid target choices."""
    return index_actions(actions)


def choose(state, goal, history):
    space = BrowserActionSpace()
    observed = space.observe(state)
    questions = space.questions(observed, goal=goal, history=history)
    body = {
        "model": os.environ.get("TYPESAFE_MODEL", "jev-latest"),
        "state": space.provider_state(observed, goal, history),
        "questions": questions,
    }
    started = time.perf_counter()
    result = post_json("https://api.typesafe.ai/v1/systemone", os.environ["TYPESAFE_API_KEY"], body)
    operation_answer = validate_choice(result["answers"].get("operation", {}), questions["operation"]["criteria"])
    answers = {"operation": operation_answer}
    operation = operation_answer["choice"]
    if operation in observed["targets"]:
        # Unused target heads cannot cause an action. Validate the head selected by the operation.
        key = operation.lower() + "_target"
        answers[key] = validate_choice(result["answers"].get(key, {}), questions[key]["criteria"])
    bound = space.bind(answers, observed)
    return {
        "choice": bound["choice"],
        "operation": bound["operation"],
        "target": bound["target"],
        "confidence": bound["confidence"],
        "probabilities": bound["probabilities"],
        "operation_probabilities": bound["operation_probabilities"],
        "target_probabilities": bound["target_probabilities"],
        "target_confidence": bound["target_confidence"],
        "raw_answers": result["answers"],
        "model": result["model"],
        "usage": result.get("usage", {}),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "request": body,
    }


def field_context(goal, action, page, history):
    return {
        "goal": goal,
        "field": {k: action.get(k) for k in ("label", "role", "value")},
        "page": {"title": page["title"], "text": page["text"][:6000]},
        "recent_actions": [{k: h.get(k) for k in ("action", "text")} for h in history[-6:]],
    }


def field_text(context):
    key = os.environ.get("TEXT_MODEL_API_KEY")
    if not key:
        raise ValueError("TYPE_TEXT needs TEXT_MODEL_API_KEY; no text is hardcoded or guessed by the executor.")
    base = os.environ.get("TEXT_MODEL_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = os.environ.get("TEXT_MODEL", "deepseek-chat")
    reasoning = {"thinking": {"type": "disabled"}} if "api.deepseek.com/" in base else {"reasoning": {"effort": "low"}}
    if os.environ.get("TEXT_MODEL_REASONING") == "none":
        reasoning = {"reasoning": {"enabled": False}}
    started = time.perf_counter()
    result = post_json(
        base + "/chat/completions",
        key,
        {
            "model": model,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
            **reasoning,
            "messages": [
                {"role": "system", "content": TEXT_VALUE},
                {
                    "role": "user",
                    "content": json.dumps(context),
                },
            ],
        },
    )
    try:
        output = json.loads(result["choices"][0]["message"]["content"])
        value = output["text"]
        if set(output) != {"text"} or not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ValueError("Text helper returned no valid field value; nothing typed.") from None
    return value, {
        "model": model,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": result.get("usage", {}),
    }
