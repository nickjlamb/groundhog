"""Model adapters. Each exposes .name and .complete(system, messages, tools) -> dict
with "text", "tool_calls" [{"id", "name", "args"}] and "usage"."""

from .mock import ScriptedModel, SubmitGoldModel


def make_model(spec: str):
    kind, _, rest = spec.partition(":")
    if kind == "mock":
        if rest in ("", "submit-gold"):
            return SubmitGoldModel()
        raise ValueError(f"unknown mock model {rest!r}")
    if kind == "anthropic":
        from .anthropic_model import AnthropicModel
        return AnthropicModel(rest)
    raise ValueError(f"unknown model spec {spec!r} (use mock:submit-gold or anthropic:<model-id>)")
