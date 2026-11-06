"""Minimal MCP client over stdio (JSON-RPC 2.0, newline-delimited)."""

import json
import subprocess


class StdioMCPClient:
    def __init__(self, command: list[str], name: str = "server"):
        self.name = name
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        self._id = 0
        info = self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                        "clientInfo": {"name": "groundhog", "version": "0.1"}})
        self.server_info = info.get("serverInfo", {})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _rpc(self, method, params=None):
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"{self.name} closed: {self.proc.stderr.read()[-2000:]}")
            try:
                reply = json.loads(line)
            except json.JSONDecodeError:
                continue
            if reply.get("id") == self._id:
                if "error" in reply:
                    raise RuntimeError(f"{self.name} {method}: {reply['error']}")
                return reply["result"]

    def list_tools(self):
        return self._rpc("tools/list")["tools"]

    def call_tool(self, name: str, args: dict):
        """Return (parsed result, is_error). Text content that is JSON is parsed."""
        res = self._rpc("tools/call", {"name": name, "arguments": args})
        texts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        joined = "\n".join(texts)
        try:
            parsed = json.loads(joined)
        except json.JSONDecodeError:
            parsed = {"text": joined}
        return parsed, bool(res.get("isError"))

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
