"""Provider contract. Hosted Jev is one implementation of this interface."""


class ProviderError(RuntimeError):
    """The provider failed before any action was executed."""


class ProviderResult:
    def __init__(self, *, answers, model_version, latency_ms, usage=None, raw=None):
        self.answers = answers
        self.model_version = model_version
        self.latency_ms = latency_ms
        self.usage = usage or {}
        self.raw = raw or {}


class ScriptedProvider:
    """Offline stand-in. Tests and replay never call a paid API."""

    def __init__(self, answers=None, model_version="scripted"):
        self.script = answers or {}
        self.model_version = model_version
        self.calls = []

    def evaluate(self, state, questions):
        self.calls.append({"state": state, "questions": questions})
        answers = self.script
        if callable(self.script):
            answers = self.script(state, questions)
        missing = set(questions) - set(answers)
        if missing:
            raise ProviderError(f"Scripted provider missing answers for {sorted(missing)}")
        return ProviderResult(
            answers={k: answers[k] for k in questions},
            model_version=self.model_version,
            latency_ms=0,
        )
