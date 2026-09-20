"""ACP JSON-RPC client talks to a fake kimi acp process. No network, no TUI scraping."""

import subprocess
import sys

from jev_ultrafast.adapters.kimi_acp import KIMI_WORKERS, KimiAcpClient

FAKE_ACP = r"""
import json, sys

def read():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode().partition(":")
        headers[key.strip().lower()] = value.strip()
    n = int(headers.get("content-length", "0"))
    return json.loads(sys.stdin.buffer.read(n))

def write(msg):
    raw = json.dumps(msg).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
    sys.stdout.buffer.flush()

while True:
    msg = read()
    if msg is None:
        break
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        write({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": 1, "agentCapabilities": {}}})
    elif method == "session/new":
        write({"jsonrpc": "2.0", "id": mid, "result": {"sessionId": "sess-1", "configOptions": [], "modes": {}}})
    elif method == "session/set_config_option":
        write({"jsonrpc": "2.0", "id": mid, "result": {}})
    elif method == "session/prompt":
        write({"jsonrpc": "2.0", "id": mid, "result": {"stopReason": "end_turn", "text": "selector is null"}})
    else:
        write({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": method}})
"""


def test_kimi_workers_map_explore_plan_coder():
    assert {spec["agent"] for spec in KIMI_WORKERS.values()} == {"explore", "plan", "coder"}
    assert KIMI_WORKERS["kimi_explore"]["readonly"] is True
    assert KIMI_WORKERS["kimi_plan"]["shell"] is False
    assert KIMI_WORKERS["kimi_coder"]["readonly"] is False


def test_acp_client_runs_an_explore_job_over_jsonrpc():
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", FAKE_ACP],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    client = KimiAcpClient(process=process)
    try:
        client.start()
        job = client.run_job("explore", "Find the selector crash")
        assert job["agent"] == "explore"
        assert job["readonly"] is True
        assert job["result"]["text"] == "selector is null"
    finally:
        process.kill()
        process.wait(timeout=5)
