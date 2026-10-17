"""Model providers behind one small interface.

  * anthropic  -- Anthropic Messages API (needs ANTHROPIC_API_KEY, `pip install anthropic`)
  * openai     -- any OpenAI-compatible chat endpoint: OpenAI, Groq, Together,
                  or a local Ollama server (OPENAI_BASE_URL / OPENAI_API_KEY)
  * scripted   -- replays canned responses; used by the test-suite and for
                  offline smoke runs. It is NOT a triage model.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass


@dataclass
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0


class Provider:
    name = "base"
    model = ""

    def complete(self, system: str, messages: list[dict]) -> Completion:  # pragma: no cover
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str | None = None, max_tokens: int = 1024):
        import anthropic  # imported lazily so the package works without it
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("TRIAGE_MODEL", "claude-sonnet-4-5")
        self.max_tokens = max_tokens

    def complete(self, system: str, messages: list[dict]) -> Completion:
        t0 = time.time()
        r = self.client.messages.create(model=self.model, system=system,
                                        messages=messages, max_tokens=self.max_tokens,
                                        temperature=0)
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return Completion(text, r.usage.input_tokens, r.usage.output_tokens, time.time() - t0)


class OpenAICompatibleProvider(Provider):
    name = "openai"

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, max_tokens: int = 1024):
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL",
                                                    "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "ollama")
        self.model = model or os.environ.get("TRIAGE_MODEL", "gpt-4o-mini")
        self.max_tokens = max_tokens

    def complete(self, system: str, messages: list[dict]) -> Completion:
        body = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
                "messages": [{"role": "system", "content": system}, *messages]}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        usage = data.get("usage", {})
        return Completion(data["choices"][0]["message"]["content"],
                          usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                          time.time() - t0)


class ScriptedProvider(Provider):
    """Returns pre-written responses in order (for tests and offline smoke runs)."""

    name = "scripted"

    def __init__(self, responses: list[str], model: str = "scripted"):
        self.responses = list(responses)
        self.model = model
        self.calls: list[list[dict]] = []

    def complete(self, system: str, messages: list[dict]) -> Completion:
        self.calls.append(list(messages))   # snapshot: the agent keeps appending
        if not self.responses:
            raise RuntimeError("ScriptedProvider ran out of responses")
        return Completion(self.responses.pop(0), 0, 0, 0.0)


def make_provider(name: str, model: str | None = None) -> Provider:
    if name == "anthropic":
        return AnthropicProvider(model)
    if name in ("openai", "ollama", "groq"):
        return OpenAICompatibleProvider(model)
    raise ValueError(f"unknown provider {name!r} (use anthropic | openai)")


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (tolerates code fences)."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced JSON in model output")
