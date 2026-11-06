"""Anthropic Messages API adapter (used for the gateway cross-check and the judge).

Requires the `anthropic` package and ANTHROPIC_API_KEY. Not exercised by the
offline tests.
"""

import json
import os


class AnthropicModel:
    def __init__(self, model_id: str, max_tokens: int = 2048):
        import anthropic  # imported lazily so offline runs need no SDK
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.name = f"anthropic:{model_id}"

    @staticmethod
    def _to_api(messages):
        out = []
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                blocks = [{"type": "text", "text": m["text"]}] if m.get("text") else []
                blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c.get("args", {})}
                           for c in m.get("tool_calls", [])]
                out.append({"role": "assistant", "content": blocks})
            elif m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"],
                         "is_error": m.get("is_error", False)}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    def complete(self, system, messages, tools):
        resp = self.client.messages.create(
            model=self.model_id, max_tokens=self.max_tokens, system=system,
            tools=[{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in tools],
            messages=self._to_api(messages),
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [{"id": b.id, "name": b.name, "args": b.input} for b in resp.content if b.type == "tool_use"]
        return {"text": text, "tool_calls": calls,
                "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}}
