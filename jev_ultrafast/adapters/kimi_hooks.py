"""Kimi lifecycle hooks emit COMPSD receipts. Fail-open. Not a security barrier."""

import json
import sys
from pathlib import Path

from ..evidence.receipts import Receipt, redact

RECEIPT_EVENTS = {
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "SessionEnd",
}

DANGEROUS_HINTS = ("rm -rf", "sudo", "mkfs", "dd if=", "shutdown", "reboot")


def looks_dangerous(payload):
    blob = json.dumps(payload).lower()
    return any(hint in blob for hint in DANGEROUS_HINTS)


def handle(payload, *, receipt_dir=None):
    """Always allow. Record a receipt. Policy/OpenShell still say no."""
    event = payload.get("hook_event_name") or payload.get("event")
    receipt = Receipt(
        "hook",
        event=event,
        known_event=event in RECEIPT_EVENTS,
        session_id=payload.get("session_id"),
        looks_dangerous=looks_dangerous(payload),
        payload=redact(payload),
        authority="none",
        fail_open=True,
    )
    directory = Path(receipt_dir or payload.get("cwd") or ".") / ".jev" / "receipts"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{receipt['receipt_id']}.json").write_text(json.dumps(receipt, indent=2))
    except OSError:
        # Fail-open: a receipt write error must not become a blocker.
        pass
    stdout = {
        "hookSpecificOutput": {
            "permissionDecision": "allow",
            "permissionDecisionReason": "Jev hook records receipts only; COMPSD/policy remain the authority.",
        },
        "receipt_id": receipt["receipt_id"],
        "looks_dangerous": receipt["looks_dangerous"],
    }
    return 0, stdout, receipt


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        code, stdout, _receipt = handle(payload)
        sys.stdout.write(json.dumps(stdout))
        sys.exit(code)
    except Exception as error:  # noqa: BLE001 — hooks must fail open
        sys.stderr.write(f"jev hook failed open: {error}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
