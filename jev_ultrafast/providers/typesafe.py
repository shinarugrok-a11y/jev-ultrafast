"""TypeSafe's hosted System One endpoint. Credentials stay in the environment; the model never sees the key."""

import os
import time

import httpx

from .base import Evaluation

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
CLIENT = httpx.Client(http2=True, timeout=25)


def post_json(url, key, body):
    for attempt in range(3):
        try:
            response = CLIENT.post(url, json=body, headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError:
            raise RuntimeError("Model connection failed; no action executed.") from None
        if response.status_code in {429, 529, 503} and attempt < 2:
            time.sleep(0.5 * 2**attempt)
            continue
        if response.is_error:
            raise RuntimeError(f"Model provider returned HTTP {response.status_code}; no action executed.")
        return response.json()
    raise RuntimeError("Model unavailable")


class TypeSafeProvider:
    name = "typesafe"

    def __init__(self, model=None, api_key=None, endpoint=ENDPOINT, post=post_json):
        self.model = model or os.environ.get("TYPESAFE_MODEL", "jev-latest")
        self._key = api_key
        self.endpoint = endpoint
        self.post = post

    def evaluate(self, state, questions):
        key = self._key or os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise ValueError("TYPESAFE_API_KEY is not configured; no decision was requested.")
        body = {"model": self.model, "state": state, "questions": {k: q.to_request() for k, q in questions.items()}}
        started = time.perf_counter()
        result = self.post(self.endpoint, key, body)
        return Evaluation(
            answers=result.get("answers", {}),
            model_version=result.get("model", self.model),
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage=result.get("usage", {}),
            request=body,
        )
