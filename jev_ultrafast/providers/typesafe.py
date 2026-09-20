"""TypeSafe hosted Jev. Credentials stay in the environment, never in requests from callers."""

import os
import time

import httpx

from ..core.validation import validate_answers
from .base import ProviderError, ProviderResult

CLIENT = httpx.Client(http2=True, timeout=25)


def post_json(url, key, body):
    for attempt in range(3):
        try:
            response = CLIENT.post(url, json=body, headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError:
            raise ProviderError("Model connection failed; no action executed.") from None
        if response.status_code in {429, 529, 503} and attempt < 2:
            time.sleep(0.5 * 2**attempt)
            continue
        if response.is_error:
            raise ProviderError(f"Model provider returned HTTP {response.status_code}; no action executed.")
        return response.json()
    raise ProviderError("Model unavailable")


class TypeSafeProvider:
    endpoint = "https://api.typesafe.ai/v1/systemone"

    def __init__(self, *, api_key=None, model=None):
        self.api_key = api_key
        self.model = model

    def evaluate(self, state, questions):
        key = self.api_key or os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise ProviderError("TYPESAFE_API_KEY is required; credentials stay server-side.")
        body = {
            "model": self.model or os.environ.get("TYPESAFE_MODEL", "jev-latest"),
            "state": state,
            "questions": questions,
        }
        started = time.perf_counter()
        result = post_json(self.endpoint, key, body)
        answers = validate_answers(
            questions, result.get("answers", {}), error="Invalid TypeSafe response; no action executed."
        )
        return ProviderResult(
            answers=answers,
            model_version=result.get("model", body["model"]),
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage=result.get("usage", {}),
            raw=result,
        )
