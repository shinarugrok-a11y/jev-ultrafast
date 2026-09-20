"""Kimi Code through ACP (JSON-RPC over stdio), not terminal scraping.

``kimi acp`` is an agent-server surface: sessions, prompts, and tool updates
travel as JSON-RPC frames. Beowulf owns the transport; this module builds and
parses frames so tests stay offline and side-effect free.

Worker mapping: ``explore`` is read-only reconnaissance, ``plan`` drafts
architecture with no shell, ``coder`` implements. Subagents run isolated and
return results to the parent handoff packet.

Hooks (SessionStart, PreToolUse, PostToolUse, SubagentStart, SubagentStop,
Stop) emit receipts automatically but are fail-open: an error or timeout
never blocks, and a hook saying "looks dangerous" is advisory. COMPSD and
deterministic policy remain the only "no".
"""

import json
import uuid

HOOKS = (
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)

SUBAGENT_ROLES = {
    "explore": "reconnaissance/read-only analysis",
    "plan": "architecture/planning with no shell",
    "coder": "implementation worker",
}


def kimi_subagent_roles():
    return dict(SUBAGENT_ROLES)


def _frame(method, params=None, msg_id=None):
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    body["id"] = msg_id if msg_id is not None else uuid.uuid4().hex
    return body


def acp_session_new(*, cwd=None):
    params = {}
    if cwd:
        params["cwd"] = cwd
    return _frame("session/new", params)


def acp_prompt(session_id, text, *, role="explore"):
    if role not in SUBAGENT_ROLES:
        raise ValueError(f"Unknown Kimi subagent role {role!r}")
    return _frame("session/prompt", {"sessionId": session_id, "role": role, "prompt": text})


def parse_message(line):
    try:
        message = json.loads(line) if isinstance(line, str) else dict(line)
    except (ValueError, TypeError):
        raise ValueError("Not a JSON-RPC frame") from None
    if message.get("jsonrpc") != "2.0":
        raise ValueError("Not a JSON-RPC frame")
    if "method" not in message and "result" not in message and "error" not in message:
        raise ValueError("Not a JSON-RPC frame")
    return message


def emit_hook_receipt(hook, payload=None):
    """Build an advisory hook receipt. Fail-open: never raises on bad input."""
    try:
        if hook not in HOOKS:
            raise ValueError(f"Unknown hook {hook!r}")
        detail = json.dumps(payload or {}, sort_keys=True, default=str)
        _ = detail
        return {"hook": hook, "advisory_only": True, "fail_open": True, "payload": payload or {}}
    except Exception:
        return {"hook": str(hook), "advisory_only": True, "fail_open": True, "payload": {}, "degraded": True}
