"""The one local System One gateway Beowulf owns.

Pepper, Kimi, Cursor, and COMPSD do not hold a TypeSafe key or invent their own Jev prompts. They POST a state
and a domain here and get back answers, distributions, confidence, model version, latency, and a policy
verdict. Every decision is logged and bound to a state hash. The gateway never sends a relay message, switches a
lane, declares DONE, approves an artifact, or authorizes an operation: the response is a recommendation.
"""

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..action_spaces import (
    AgentRoutingActionSpace,
    BrowserActionSpace,
    ComputerActionSpace,
    RelayActionSpace,
    RepoActionSpace,
    evaluate_space,
)
from ..action_spaces.base import ActionSpace, Recommendation
from ..core.decision import DecisionLedger
from ..core.questions import STANDARD_QUESTIONS
from ..evidence.traces import TraceWriter
from ..policy import default_policy, forbidden_changes
from ..providers import TypeSafeProvider


class QuestionSetSpace(ActionSpace):
    """Ask standard questions directly about an arbitrary state. No operation, no target."""

    domain = "questions"

    def __init__(self, state, question_ids):
        unknown = [q for q in question_ids if q not in STANDARD_QUESTIONS]
        if unknown or not question_ids:
            raise ValueError(f"Unknown or empty question ids: {unknown}")
        self._state, self.ids = state, list(question_ids)

    def state(self):
        return self._state

    def questions(self):
        return {qid: STANDARD_QUESTIONS[qid] for qid in self.ids}

    def resolve(self, answers):
        flags, scores = self.flags_and_scores(self.questions(), answers)
        choices = {k: a["choice"] for k, a in answers.items() if "choice" in a}
        return Recommendation(self.domain, "ANSWER", flags=flags, scores=scores, answers={**answers, **choices})


def build_space(domain, payload):
    if domain == "relay":
        return RelayActionSpace(
            payload["thread"], payload["identity"], payload.get("recent_sends", ()), payload.get("operations")
        )
    if domain == "agent_router":
        return AgentRoutingActionSpace(payload["packet"], payload["available_executors"], payload.get("sleeping_agent"))
    if domain == "repository":
        return RepoActionSpace(payload["request"], payload["files"], payload.get("tests"), payload.get("branch"))
    if domain == "computer":
        return ComputerActionSpace(payload["observation"], payload["goal"], payload.get("history", ()))
    if domain == "browser":
        return BrowserActionSpace(payload["page"], payload["goal"], payload.get("history", ()))
    if domain == "questions":
        return QuestionSetSpace(payload["state"], payload["question_ids"])
    raise ValueError(f"Unknown decision domain {domain!r}")


class SystemOneGateway:
    def __init__(self, provider, policy=None, ledger=None, trace=None):
        self.provider = provider
        self.policy = policy or default_policy()
        self.ledger = ledger or DecisionLedger()
        self.trace = trace or TraceWriter()

    def decide(self, request):
        domain, payload = request["domain"], request.get("input", {})
        context = request.get("policy_context", {})
        space = build_space(domain, payload)
        with self.trace.span("jev.decide", domain=domain) as span:
            recommendation, decision, evaluation = evaluate_space(space, self.provider, self.ledger)
            categories = list(context.get("categories", []))
            if domain == "repository":
                blocked = forbidden_changes([f["path"] for f in payload["files"]], context.get("protected_paths", {}))
                if blocked:
                    categories.extend(blocked)
                    span.event("protected_paths", matches=blocked)
            outcome = self.policy.evaluate(
                recommendation,
                categories=categories,
                model_version=context.get("model_version"),
                extra_gates=context.get("gates"),
            )
            self.trace.annotate_decision(span, decision, recommendation, outcome)
        questions = space.questions()
        return {
            "decision_id": decision.decision_id,
            "state_hash": decision.state_hash,
            "domain": domain,
            "recommendation": recommendation.to_dict(),
            "answers": decision.answers,
            "distributions": {
                k: a.get("probabilities", {"true": a["noul"], "false": 1 - a["noul"]} if "noul" in a else {})
                for k, a in decision.answers.items()
            },
            "confidence": recommendation.confidence,
            "policy": outcome.to_dict(),
            "calibration": {
                q.id: (self.policy.locks[q.id].status if q.id in self.policy.locks else "none")
                for q in questions.values()
            },
            "model_version": evaluation.model_version,
            "latency_ms": evaluation.latency_ms,
            "usage": evaluation.usage,
            "authority": "recommendation",
        }

    def consume(self, decision_id, state, requested_action):
        decision = self.ledger.consume(decision_id, state, requested_action)
        return {"decision_id": decision.decision_id, "consumed_at": decision.consumed_at}

    def result(self, decision_id, receipt):
        decision = self.ledger.record_result(decision_id, receipt)
        return {"decision_id": decision.decision_id, "result_receipt": decision.result_receipt}


def serve(gateway, port, token=None):
    """Loopback-only HTTP surface: POST /decision, /consume, /result. Mirrors the demo's local request guards."""
    token = token or secrets.token_urlsafe(32)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, payload):
            content = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self):
            if self.headers.get("Host") != self.server.host or self.headers.get("X-Gateway-Token") != token:
                return self.send(403, {"error": "Local gateway requests only"})
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 1_000_000:
                return self.send(400, {"error": "Invalid request size"})
            try:
                body = json.loads(self.rfile.read(length))
                with lock:
                    if self.path == "/decision":
                        result = gateway.decide(body)
                    elif self.path == "/consume":
                        result = gateway.consume(body["decision_id"], body["state"], body["requested_action"])
                    elif self.path == "/result":
                        result = gateway.result(body["decision_id"], body["receipt"])
                    else:
                        return self.send(404, {"error": "Unknown endpoint"})
                self.send(200, result)
            except (ValueError, KeyError, LookupError, RuntimeError) as error:
                self.send(400, {"error": str(error)})

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.token = token
    server.host = f"127.0.0.1:{server.server_address[1]}"
    return server


def main():
    port = int(os.environ.get("JEV_GATEWAY_PORT", "8767"))
    log = os.environ.get("JEV_DECISION_LOG", "artifacts/decisions.jsonl")
    os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
    gateway = SystemOneGateway(TypeSafeProvider(), ledger=DecisionLedger(log), trace=TraceWriter(log + ".trace"))
    server = serve(gateway, port, os.environ.get("JEV_GATEWAY_TOKEN"))
    print(f"Jev gateway: http://{server.host}  token={server.token}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
