"""Gemini API adapter (Google AI Studio / generativelanguage.googleapis.com).

Calls Google's own endpoint, so Gemini results no longer depend on a gateway.
Gemini 3 models return a thoughtSignature with function calls that must be sent
back unchanged on the next turn; the adapter keeps each turn's raw parts on the
first tool call and replays them.

Spending cap: every call's cost is estimated from the token counts Google
returns (thinking tokens are billed as output) and added to a ledger,
runs/gemini_spend.json. A call that would start with the ledger at or above
GEMINI_BUDGET_USD (default 70) raises BudgetExceeded instead of spending.

Needs GEMINI_API_KEY. Uses only the standard library.
"""

import itertools
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
LEDGER = Path(__file__).resolve().parents[2] / "runs" / "gemini_spend.json"

# USD per million tokens (input, output). Unknown models get the Pro price, so
# the cap errs towards stopping early rather than overspending.
PRICES = {
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3.5-flash": (0.75, 3.75),
    "gemini-4-argon": (2.00, 10.00),      # third-party snapshot, Oct 2026; reported to double on 1 Dec 2026
    "gemini-3.8-flash": (0.75, 3.75),
}
DEFAULT_PRICE = (2.00, 12.00)

RETRY_WAITS = (5, 20, 60, 120, None)
MIN_INTERVAL = 1.0
_last = [0.0]
_ids = itertools.count(1)


class BudgetExceeded(RuntimeError):
    pass


def spent() -> float:
    try:
        return json.loads(LEDGER.read_text())["usd"]
    except (OSError, ValueError, KeyError):
        return 0.0


def _add_spend(usd: float, model: str):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    data = {"usd": 0.0, "by_model": {}}
    try:
        data = json.loads(LEDGER.read_text())
    except (OSError, ValueError):
        pass
    data["usd"] = round(data.get("usd", 0.0) + usd, 6)
    data.setdefault("by_model", {})[model] = round(data["by_model"].get(model, 0.0) + usd, 6)
    LEDGER.write_text(json.dumps(data, indent=1))


def cost_usd(model: str, usage: dict) -> float:
    pin, pout = PRICES.get(model, DEFAULT_PRICE)
    out = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
    return (usage.get("promptTokenCount", 0) * pin + out * pout) / 1e6


def to_contents(messages: list[dict]) -> list[dict]:
    contents, names = [], {}
    for m in messages:
        if m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            calls = m.get("tool_calls") or []
            for c in calls:
                names[c["id"]] = c["name"]
            raw = calls[0].get("_raw_parts") if calls else m.get("_raw_parts")
            if raw:
                parts = raw
            else:
                parts = ([{"text": m["text"]}] if m.get("text") else []) + \
                        [{"functionCall": {"name": c["name"], "args": c.get("args", {})}} for c in calls]
            if parts:
                contents.append({"role": "model", "parts": parts})
        elif m["role"] == "tool":
            part = {"functionResponse": {"name": names.get(m["tool_call_id"], "tool"),
                                         "response": {"content": m["content"]}}}
            if contents and contents[-1]["role"] == "user" and "functionResponse" in contents[-1]["parts"][0]:
                contents[-1]["parts"].append(part)          # parallel calls: one turn of responses
            else:
                contents.append({"role": "user", "parts": [part]})
    return contents


def to_tools(tools: list[dict]) -> list[dict]:
    return [{"functionDeclarations": [{"name": t["name"], "description": t["description"],
                                       "parametersJsonSchema": t["input_schema"]} for t in tools]}]


def parse_response(body: dict, model: str) -> dict:
    cand = (body.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
    calls = []
    for p in parts:
        if "functionCall" in p:
            fc = p["functionCall"]
            calls.append({"id": fc.get("id") or f"gem_{next(_ids)}", "name": fc["name"], "args": fc.get("args") or {}})
    if calls:
        calls[0]["_raw_parts"] = parts
    u = body.get("usageMetadata") or {}
    usage = {"input_tokens": u.get("promptTokenCount", 0),
             "output_tokens": u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0),
             "cost_usd": cost_usd(model, u)}
    return {"text": text, "tool_calls": calls, "usage": usage,
            "model_served": body.get("modelVersion"), "finish_reason": cand.get("finishReason")}


class GeminiModel:
    def __init__(self, model_id: str, max_output_tokens: int = 8192, timeout: int = 180):
        self.model_id = model_id
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout
        self.name = f"gemini:{model_id}"
        self.key = os.environ["GEMINI_API_KEY"]
        self.budget = float(os.environ.get("GEMINI_BUDGET_USD", "70"))

    def complete(self, system, messages, tools):
        if spent() >= self.budget:
            raise BudgetExceeded(f"Gemini spend ${spent():.2f} has reached the ${self.budget:.2f} cap")
        payload = {"systemInstruction": {"parts": [{"text": system}]}, "contents": to_contents(messages),
                   "tools": to_tools(tools), "generationConfig": {"maxOutputTokens": self.max_output_tokens}}
        req = urllib.request.Request(ENDPOINT.format(model=self.model_id), data=json.dumps(payload).encode(),
                                     method="POST", headers={"x-goog-api-key": self.key,
                                                             "Content-Type": "application/json"})
        for wait in RETRY_WAITS:
            gap = time.time() - _last[0]
            if gap < MIN_INTERVAL:
                time.sleep(MIN_INTERVAL - gap)
            _last[0] = time.time()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = parse_response(json.loads(r.read()), self.model_id)
                _add_spend(out["usage"]["cost_usd"], self.model_id)
                return out
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or wait is None:
                    detail = e.read().decode(errors="replace")[:500]
                    raise RuntimeError(f"Gemini API {e.code}: {detail}") from None
                time.sleep(wait)
            except (urllib.error.URLError, TimeoutError):
                if wait is None:
                    raise
                time.sleep(wait)
