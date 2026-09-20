"""Kimi Code via ACP JSON-RPC over stdin/stdout. Never scrape a TUI."""

import json
import os
import subprocess
import threading

KIMI_WORKERS = {
    "kimi_explore": {"agent": "explore", "readonly": True, "shell": False},
    "kimi_plan": {"agent": "plan", "readonly": True, "shell": False},
    "kimi_coder": {"agent": "coder", "readonly": False, "shell": True},
}


class AcpError(RuntimeError):
    pass


def encode_message(payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


def read_message(stream):
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode().partition(":")
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = stream.read(length)
    return json.loads(body)


class KimiAcpClient:
    """Drive `kimi acp` as a JSON-RPC agent-server. Credentials stay in Kimi's own login."""

    def __init__(self, command=None, *, cwd=None, process=None):
        self.command = command or ["kimi", "acp"]
        self.cwd = cwd or os.getcwd()
        self.process = process
        self._id = 0
        self._lock = threading.Lock()
        self.sessions = {}
        self.notifications = []

    def start(self):
        if self.process is None:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
            )
        result = self.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {}, "terminal": {}},
                "clientInfo": {"name": "jev-ultrafast", "version": "0.2.0"},
            },
        )
        return result

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def request(self, method, params=None):
        with self._lock:
            self._id += 1
            message_id = self._id
            payload = {"jsonrpc": "2.0", "id": message_id, "method": method, "params": params or {}}
            self.process.stdin.write(encode_message(payload))
            self.process.stdin.flush()
            while True:
                message = read_message(self.process.stdout)
                if message is None:
                    raise AcpError("ACP stream closed")
                if message.get("method"):
                    self.notifications.append(message)
                    continue
                if message.get("id") != message_id:
                    continue
                if message.get("error"):
                    raise AcpError(message["error"])
                return message.get("result")

    def new_session(self, *, cwd=None, mcp_servers=None):
        result = self.request("session/new", {"cwd": cwd or self.cwd, "mcpServers": mcp_servers or []})
        session_id = result["sessionId"]
        self.sessions[session_id] = result
        return result

    def prompt(self, session_id, text, *, agent=None):
        if agent:
            self.request("session/set_config_option", {"sessionId": session_id, "configId": "mode", "value": agent})
        return self.request("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]})

    def run_job(self, agent, prompt, *, cwd=None):
        """Map Beowulf jobs onto Kimi's explore / plan / coder workers."""
        if agent not in {spec["agent"] for spec in KIMI_WORKERS.values()}:
            raise ValueError(f"Unknown Kimi worker {agent}")
        session = self.new_session(cwd=cwd)
        result = self.prompt(session["sessionId"], prompt, agent=agent)
        return {
            "agent": agent,
            "session_id": session["sessionId"],
            "result": result,
            "readonly": next(spec["readonly"] for spec in KIMI_WORKERS.values() if spec["agent"] == agent),
            "kind": "kimi_job",
        }
