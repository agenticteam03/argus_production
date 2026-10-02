"""LLMPort adapters: OpenAI Responses API (default), OpenAI chat-completions dialect, scripted (tests).
Only ModelReply crosses the port. GPT-5.x reasoning models refuse function tools on /v1/chat/completions,
so the Responses API is the default; the chat dialect stays for OpenAI-compatible providers."""
from __future__ import annotations

import json
import time
from typing import Callable

from argus.ports.ports import ModelMessage, ModelReply, ModelToolCall, ModelToolDefinition, Usage


class OpenAIChat:
    def __init__(self, api_key: str, model: str, base_url: str | None = None, timeout_s: float = 120,
                 extra_params: dict | None = None, retries: int = 2):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout_s)
        self.model = model
        self.extra = extra_params or {}          # e.g. temperature only when the model accepts it
        self.retries = retries

    def decide(self, messages: list[ModelMessage], tools: list[ModelToolDefinition]) -> ModelReply:
        payload = dict(model=self.model, messages=[m.model_dump() for m in messages],
                       tools=[{"type": "function", "function": {"name": t.name, "description": t.description,
                                                                "parameters": t.parameters_schema}} for t in tools],
                       tool_choice="required", **self.extra)
        r = _with_retry(lambda: self.client.chat.completions.create(**payload), self.retries)
        ch = r.choices[0]
        calls = [ModelToolCall(name=c.function.name, arguments_json=c.function.arguments or "{}")
                 for c in (ch.message.tool_calls or [])]
        fr = ch.finish_reason if ch.finish_reason in ("stop", "tool_calls", "length", "content_filter") else "stop"
        u = getattr(r, "usage", None)
        return ModelReply(text=ch.message.content, tool_calls=calls, finish_reason=fr,
                          usage=Usage(input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                                      output_tokens=getattr(u, "completion_tokens", 0) or 0))


def _with_retry(call, retries: int):
    """Bounded retry on transient provider errors; a 4xx request error is permanent and raised at once."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return call()
        except Exception as e:
            status = getattr(e, "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                raise
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]


class OpenAIResponses:
    """OpenAI Responses API (/v1/responses): required for function tools with GPT-5.x reasoning models."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None, timeout_s: float = 120,
                 extra_params: dict | None = None, retries: int = 2):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout_s)
        self.model = model
        self.extra = extra_params or {}          # e.g. {"reasoning": {"effort": "low"}}
        self.retries = retries

    def decide(self, messages: list[ModelMessage], tools: list[ModelToolDefinition]) -> ModelReply:
        payload = dict(model=self.model, input=[{"role": m.role, "content": m.content} for m in messages],
                       tools=[{"type": "function", "name": t.name, "description": t.description,
                               "parameters": t.parameters_schema, "strict": False} for t in tools],
                       tool_choice="required", **self.extra)
        return self.parse(_with_retry(lambda: self.client.responses.create(**payload), self.retries))

    @staticmethod
    def parse(r) -> ModelReply:
        calls, texts = [], []
        for item in getattr(r, "output", None) or []:
            kind = getattr(item, "type", None)
            if kind == "function_call":
                calls.append(ModelToolCall(name=item.name, arguments_json=item.arguments or "{}"))
            elif kind == "message":
                texts += [c.text for c in (item.content or []) if getattr(c, "type", None) == "output_text"]
        if calls:
            fr = "tool_calls"
        elif getattr(r, "status", None) == "incomplete":
            reason = getattr(getattr(r, "incomplete_details", None), "reason", None)
            fr = "content_filter" if reason == "content_filter" else "length"
        else:
            fr = "stop"
        u = getattr(r, "usage", None)
        return ModelReply(text="\n".join(texts) or None, tool_calls=calls, finish_reason=fr,
                          usage=Usage(input_tokens=getattr(u, "input_tokens", 0) or 0,
                                      output_tokens=getattr(u, "output_tokens", 0) or 0))


class ScriptedLLM:
    """Replays a list of replies (or a function of the context) — offline tests."""

    def __init__(self, replies: list[dict] | Callable[[str], dict]):
        self.replies = replies
        self.calls = 0

    def decide(self, messages: list[ModelMessage], tools: list[ModelToolDefinition]) -> ModelReply:
        self.calls += 1
        spec = self.replies(messages[-1].content) if callable(self.replies) else self.replies[self.calls - 1]
        return ModelReply(text=spec.get("text"), finish_reason=spec.get("finish_reason", "tool_calls"),
                          tool_calls=[ModelToolCall(name=n, arguments_json=json.dumps(a))
                                      for n, a in spec.get("calls", [])])
