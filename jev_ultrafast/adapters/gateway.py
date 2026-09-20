"""Local System One gateway. Recommendations only. Beowulf owns the TypeSafe key."""

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..action_spaces import get_space
from ..core.decision import AlreadyConsumed, DecisionLedger, StaleDecision
from ..core.questions import as_wire
from ..core.validation import confidences, distributions, validate_answers
from ..evidence.receipts import redact
from ..evidence.traces import Trace
from ..providers.base import ScriptedProvider

PORT = int(os.environ.get("JEV_GATEWAY_PORT", "8767"))
ORIGIN = f"http://127.0.0.1:{PORT}"
TOKEN = os.environ.get("JEV_GATEWAY_TOKEN") or secrets.token_urlsafe(32)


class SystemOneGateway:
    """In-process decision service. Never sends, executes, approves, or declares DONE."""

    forbidden = ("send_relay", "resend_relay", "switch_lane", "declare_done", "approve_artifact", "authorize_operation")

    def __init__(self, provider=None, *, policy_version="beowulf.v1", log_path=None):
        self.provider = provider or ScriptedProvider()
        self.policy_version = policy_version
        self.ledger = DecisionLedger()
        self.log_path = Path(log_path) if log_path else None
        self.trace = Trace("jev.gateway")
        self.calls = []

    def decide(self, state, questions=None, policy_context=None, *, goal="", history=None):
        policy_context = policy_context or {}
        space = None
        observed = state
        if policy_context.get("domain"):
            space = get_space(policy_context["domain"])
            observed = space.observe(state)
            questions = space.questions(observed, goal=goal or policy_context.get("goal", ""), history=history)
            state = dict(observed)
        wire = as_wire(questions or {})
        started = time.perf_counter()
        result = self.provider.evaluate(state, wire)
        answers = validate_answers(wire, result.answers)
        bound = space.bind(answers, observed) if space else None
        record = self.ledger.remember(
            state=state,
            answers=answers,
            questions=wire,
            model_version=result.model_version,
            policy_version=self.policy_version,
            latency_ms=result.latency_ms or round((time.perf_counter() - started) * 1000),
            usage=result.usage,
            extra={"bound": bound, "policy_context": redact(policy_context), "domain": policy_context.get("domain")},
        )
        self.trace.annotate_decision(record)
        payload = {
            "decision_id": record["decision_id"],
            "state_hash": record["state_hash"],
            "answers": answers,
            "distributions": distributions(answers),
            "confidence": confidences(answers),
            "model_version": result.model_version,
            "policy_version": self.policy_version,
            "latency_ms": record["latency_ms"],
            "bound": bound,
            "kind": "recommendation",
            "consumed_at": None,
        }
        self.calls.append(payload)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as handle:
                handle.write(json.dumps(redact(payload)) + "\n")
        return payload

    def consume(self, decision_id, state, requested_action):
        if requested_action and requested_action.get("kind") in self.forbidden:
            raise ValueError("Gateway will not consume a forbidden action")
        return self.ledger.consume(decision_id, state, requested_action)

    def receipt(self, decision_id, receipt):
        return self.ledger.attach_receipt(decision_id, receipt)


def load_environment():
    path = Path.cwd() / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value.strip())


def default_provider():
    if os.environ.get("JEV_PROVIDER", "typesafe") == "scripted":
        return ScriptedProvider()
    from ..providers.typesafe import TypeSafeProvider

    return TypeSafeProvider()


GATEWAY = None
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, mime="application/json"):
        content = content if isinstance(content, bytes) else content.encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def _authorized(self):
        return (
            self.headers.get("Host") == f"127.0.0.1:{PORT}"
            and self.headers.get("X-Gateway-Token") == TOKEN
            and self.headers.get("Origin") in (None, ORIGIN)
        )

    def do_GET(self):
        if self.headers.get("Host") != f"127.0.0.1:{PORT}":
            return self.send(403, "Forbidden", "text/plain")
        if urlparse(self.path).path == "/health":
            return self.send(200, json.dumps({"ok": True, "kind": "recommendation"}))
        return self.send(404, "Not found", "text/plain")

    def do_POST(self):
        if not self._authorized():
            return self.send(403, json.dumps({"error": "Local gateway requests only"}))
        if not LOCK.acquire(blocking=False):
            return self.send(409, json.dumps({"error": "A decision is already running"}))
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 1_000_000:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            path = urlparse(self.path).path
            if path == "/decision":
                result = GATEWAY.decide(
                    body.get("state"),
                    body.get("questions"),
                    body.get("policy_context"),
                    goal=body.get("goal", ""),
                    history=body.get("history"),
                )
            elif path == "/consume":
                result = GATEWAY.consume(body["decision_id"], body["state"], body.get("requested_action"))
            elif path == "/receipt":
                result = GATEWAY.receipt(body["decision_id"], body["receipt"])
            else:
                return self.send(404, json.dumps({"error": "Not found"}))
            self.send(200, json.dumps(result))
        except (ValueError, KeyError, StaleDecision, AlreadyConsumed) as error:
            self.send(400, json.dumps({"error": str(error)}))
        except Exception:
            self.send(500, json.dumps({"error": "Gateway failed; no action executed."}))
        finally:
            LOCK.release()

    def log_message(self, *_args):
        pass


def main():
    global GATEWAY
    load_environment()
    GATEWAY = SystemOneGateway(default_provider())
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"JEV System One gateway: {ORIGIN}", flush=True)
    print("Recommendations only. Token required on X-Gateway-Token.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
