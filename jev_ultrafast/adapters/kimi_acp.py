"""Kimi Code over ACP (JSON-RPC 2.0 on stdin/stdout), plus hook payloads turned into receipts.

``kimi acp`` is a proper agent-server surface: initialize, session/new, session/prompt, session/cancel, and
streamed session/update notifications. Tool approval arrives as a reverse request, session/request_permission,
which this adapter answers from a deterministic per-worker policy. Kimi's three built-in sub-agents map to
Beowulf jobs: explore (read-only reconnaissance), plan (architecture, no shell), coder (bounded implementation).

Hooks are fail-open by Kimi's own documentation, so they only ever produce receipts and advisory denials here.
The thing capable of saying no is the permission policy plus COMPSD/OpenShell, never a hook.
"""

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

from ..evidence.receipts import Receipt
from ..policy import categories_for_command

WORKERS = {
    "explore": {"description": "Read-only reconnaissance", "allowed_kinds": {"read", "search", "fetch", "think"}},
    "plan": {"description": "Planning without shell or edits", "allowed_kinds": {"read", "search", "think"}},
    "coder": {
        "description": "Bounded implementation",
        "allowed_kinds": {"read", "search", "fetch", "think", "edit", "move", "execute", "other"},
    },
}

DENY_KINDS = {"reject_once", "reject_always"}
ALLOW_KINDS = {"allow_once", "allow_always"}


@dataclass
class Job:
    kind: str
    task: str
    cwd: str
    job_id: str = field(default_factory=lambda: f"job-{int(time.time() * 1000)}")

    def __post_init__(self):
        if self.kind not in WORKERS:
            raise ValueError(f"Unknown Kimi worker {self.kind!r}; expected one of {sorted(WORKERS)}")

    def prompt(self):
        """The request text. Sub-agent selection is an instruction; enforcement is the permission policy."""
        return (
            f"Use the `{self.kind}` sub-agent for this job and return its result as your final message.\n"
            f"Job {self.job_id}. {WORKERS[self.kind]['description']}.\n\n{self.task}"
        )


class WorkerPolicy:
    """Answers session/request_permission deterministically from the job's worker kind."""

    def __init__(self, job):
        self.job = job
        self.decisions = []

    def decide(self, tool_call, options):
        kind = str(tool_call.get("kind", "other"))
        title = str(tool_call.get("title", ""))
        command = json.dumps(tool_call.get("rawInput", tool_call.get("content", "")))
        allowed = kind in WORKERS[self.job.kind]["allowed_kinds"]
        categories = categories_for_command(command) or categories_for_command(title)
        if categories:
            allowed = False  # HUMAN_REQUIRED categories are never approved by an adapter.
        wanted = ALLOW_KINDS if allowed else DENY_KINDS
        option = next((o for o in options if o.get("kind") in wanted), None)
        if option is None and allowed:
            option = next((o for o in options if o.get("kind") in DENY_KINDS), None)
            allowed = False
        record = {"tool_kind": kind, "title": title, "allowed": allowed, "categories": categories}
        self.decisions.append(record)
        if option is None:
            return {"outcome": {"outcome": "cancelled"}}, record
        return {"outcome": {"outcome": "selected", "optionId": option["optionId"]}}, record


class KimiACP:
    def __init__(self, job, command=("kimi", "acp"), popen=subprocess.Popen, on_update=None, timeout=600):
        self.job = job
        self.command = list(command)
        self.popen = popen
        self.on_update = on_update
        self.timeout = timeout
        self.policy = WorkerPolicy(job)
        self.process = None
        self.updates = []
        self._next_id = 0
        self._responses = {}
        self._lock = threading.Lock()
        self._reader = None

    def start(self):
        self.process = self.popen(
            self.command, cwd=self.job.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return self.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "jev-ultrafast", "version": "0.2"},
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
            },
        )

    def new_session(self, mcp_servers=()):
        result = self.request("session/new", {"cwd": self.job.cwd, "mcpServers": list(mcp_servers)})
        return result["sessionId"]

    def prompt(self, session_id, text=None):
        result = self.request(
            "session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": text or self.job.prompt()}]}
        )
        chunks = [
            u["update"]["content"]["text"]
            for u in self.updates
            if u.get("sessionId") == session_id
            and u.get("update", {}).get("sessionUpdate") == "agent_message_chunk"
            and u["update"].get("content", {}).get("type") == "text"
        ]
        tool_calls = [u["update"] for u in self.updates if u.get("update", {}).get("sessionUpdate") == "tool_call"]
        return {
            "stop_reason": result.get("stopReason"),
            "text": "".join(chunks),
            "tool_calls": tool_calls,
            "permissions": list(self.policy.decisions),
        }

    def cancel(self, session_id):
        self._send({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})

    def close(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
            self.process.terminate()

    def request(self, method, params):
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            event = threading.Event()
            self._responses[request_id] = [event, None]
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        if not event.wait(self.timeout):
            raise TimeoutError(f"ACP {method} timed out")
        message = self._responses.pop(request_id)[1]
        if "error" in message:
            raise RuntimeError(f"ACP {method} failed: {message['error']}")
        return message.get("result", {})

    def _send(self, message):
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()

    def _read_loop(self):
        for raw in self.process.stdout:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if "id" in message and "method" not in message:
                pending = self._responses.get(message["id"])
                if pending:
                    pending[1] = message
                    pending[0].set()
            elif "method" in message and "id" in message:
                self._handle_request(message)
            elif message.get("method") == "session/update":
                self.updates.append(message.get("params", {}))
                if self.on_update:
                    self.on_update(message["params"])

    def _handle_request(self, message):
        method, params = message["method"], message.get("params", {})
        if method == "session/request_permission":
            result, _record = self.policy.decide(params.get("toolCall", {}), params.get("options", []))
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})
        else:
            # fs/* and terminal/* were not advertised. Kimi runs those itself; we do not proxy them.
            self._send(
                {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": f"{method} not supported"}}
            )


def run_job(job, **kwargs):
    """Start Kimi, run one prompt, return the result and the permission decisions that were made."""
    client = KimiACP(job, **kwargs)
    try:
        client.start()
        session = client.new_session()
        result = client.prompt(session)
        result["session_id"] = session
        return result
    finally:
        client.close()


def hook_receipt(payload, issuer="kimi-hook"):
    """Turn a Kimi hook payload (stdin JSON) into a receipt. Hooks observe; they do not authorize."""
    event = payload.get("hook_event_name", "unknown")
    subject = payload.get("session_id", "unknown-session")
    evidence = {
        "event": event,
        "tool_name": payload.get("tool_name"),
        "matcher": payload.get("matcher"),
        "cwd": payload.get("cwd"),
        "session_title": payload.get("session_title"),
        "subagent": payload.get("agent_name") or payload.get("subagent_name"),
    }
    command = (payload.get("tool_input") or {}).get("command")
    if command:
        evidence["categories"] = categories_for_command(command)
    return Receipt("transport" if event.startswith("Subagent") else "file", subject, issuer, evidence)


def hook_main(stdin=sys.stdin, stdout=sys.stdout):
    """`python -m jev_ultrafast.adapters.kimi_acp` as a Kimi hook command. Always exits 0; advisory only."""
    try:
        payload = json.loads(stdin.read() or "{}")
    except ValueError:
        return 0
    receipt = hook_receipt(payload)
    path = os.environ.get("JEV_RECEIPTS")
    if path:
        with open(path, "a") as handle:
            handle.write(json.dumps(receipt.to_dict()) + "\n")
    categories = receipt.evidence.get("categories")
    if payload.get("hook_event_name") == "PreToolUse" and categories:
        advisory = {
            "hookSpecificOutput": {
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Human-required categories {categories}; hooks are fail-open, "
                "so this is advisory. Permission policy decides.",
            }
        }
        stdout.write(json.dumps(advisory) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(hook_main())
