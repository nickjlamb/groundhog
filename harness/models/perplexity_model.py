"""Perplexity Agent API adapter: the single gateway for every model in the
main run (design spec section 4a).

POST https://api.perplexity.ai/v1/agent, Responses-style: custom tools are
{"type": "function", "name", "description", "parameters"}; the model returns
"function_call" items (call_id, name, arguments as a JSON string); results go
back as "function_call_output" items. Each request resends the whole
conversation, so no server-side state is relied on.

Needs PERPLEXITY_API_KEY. Uses only the standard library.
"""

import json
import os
import urllib.request

ENDPOINT = "https://api.perplexity.ai/v1/agent"


def to_input(messages: list[dict]) -> list[dict]:
    items = []
    for m in messages:
        if m["role"] == "user":
            items.append({"type": "message", "role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            if m.get("text"):
                items.append({"type": "message", "role": "assistant", "content": m["text"]})
            for c in m.get("tool_calls", []):
                items.append({"type": "function_call", "call_id": c["id"], "name": c["name"],
                              "arguments": json.dumps(c.get("args", {}), ensure_ascii=False)})
        elif m["role"] == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"], "output": m["content"]})
    return items


def to_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
            for t in tools]


def parse_response(body: dict) -> dict:
    text, calls = [], []
    for item in body.get("output", []) or []:
        if item.get("type") == "message":
            for part in item.get("content", []) or []:
                if part.get("type") in ("output_text", "text"):
                    text.append(part.get("text", ""))
        elif item.get("type") == "function_call":
            try:
                args = json.loads(item.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_unparsed_arguments": item.get("arguments")}
            calls.append({"id": item["call_id"], "name": item["name"], "args": args})
    u = body.get("usage", {}) or {}
    usage = {"input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
             "cost_usd": (u.get("cost") or {}).get("total_cost", 0.0)}
    return {"text": "".join(text), "tool_calls": calls, "usage": usage, "model_served": body.get("model")}


class PerplexityModel:
    def __init__(self, model_id: str, max_output_tokens: int = 4096, timeout: int = 180):
        self.model_id = model_id
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout
        self.name = f"perplexity:{model_id}"
        self.key = os.environ["PERPLEXITY_API_KEY"]

    def complete(self, system, messages, tools):
        payload = {"model": self.model_id, "instructions": system, "input": to_input(messages),
                   "tools": to_tools(tools), "max_output_tokens": self.max_output_tokens, "store": False}
        req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return parse_response(json.loads(r.read()))
