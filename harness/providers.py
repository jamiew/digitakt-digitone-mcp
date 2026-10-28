"""LLM adapters: one small class per API, each owning its own message history.

- Anthropic: Messages API.
- OpenAI: Responses API. Chat Completions only allows tool calls on current
  models with reasoning turned off, so it isn't used for OpenAI itself.
- OpenRouter: its OpenAI-compatible Chat Completions endpoint.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic
import openai
from mcp.types import Tool

OPENROUTER_URL = "https://openrouter.ai/api/v1"

# Provider name -> (API key variable, default model).
PROVIDERS = {
    "anthropic": ("ANTHROPIC_API_KEY", "claude-sonnet-5-5"),
    "openai": ("OPENAI_API_KEY", "gpt-6-luna"),
    "openrouter": ("OPENROUTER_API_KEY", "anthropic/claude-sonnet-5.5"),
}

MAX_TOKENS = 4096


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolOutcome:
    call: ToolCall
    text: str
    is_error: bool
    arguments: dict[str, Any] = field(default_factory=dict)
    """What the tool actually ran with: the call's arguments over the schema defaults."""


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class Provider(Protocol):
    label: str

    def add_user(self, text: str) -> None: ...
    async def complete(self) -> Reply: ...
    def add_tool_results(self, outcomes: list[ToolOutcome]) -> None: ...


def pick_provider(requested: str | None) -> str:
    """The requested provider, else the first one with an API key in the environment."""
    if requested:
        key = PROVIDERS[requested][0]
        if not os.environ.get(key):
            raise SystemExit(f"{requested} needs {key} set.")
        return requested
    for name, (key, _) in PROVIDERS.items():
        if os.environ.get(key):
            return name
    keys = ", ".join(key for key, _ in PROVIDERS.values())
    raise SystemExit(f"No API key found. Set one of {keys} (a .env file in the repo root works too).")


def make_provider(name: str, model: str | None, system: str, tools: list[Tool]) -> Provider:
    """Build a provider for `name`, which pick_provider has already checked has a key."""
    key, default_model = PROVIDERS[name]
    model = model or default_model
    if name == "anthropic":
        return AnthropicProvider(model, system, tools)
    if name == "openai":
        return OpenAIProvider(model, system, tools)
    return ChatCompletionsProvider(
        model, system, tools, client=openai.AsyncOpenAI(base_url=OPENROUTER_URL, api_key=os.environ[key])
    )


def _arguments(raw: str | None) -> dict[str, Any]:
    parsed = json.loads(raw or "{}")
    return parsed if isinstance(parsed, dict) else {}


class AnthropicProvider:
    def __init__(self, model: str, system: str, tools: list[Tool]) -> None:
        self.label = f"anthropic/{model}"
        self.model = model
        self.system = system
        self.client = anthropic.AsyncAnthropic()
        self.tools: list[Any] = [
            {"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in tools
        ]
        # Tools and system prompt are identical on every request; cache them.
        self.tools[-1]["cache_control"] = {"type": "ephemeral"}
        self.messages: list[Any] = []

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    async def complete(self) -> Reply:
        response = await self.client.messages.create(
            model=self.model, max_tokens=MAX_TOKENS, system=self.system, tools=self.tools, messages=self.messages
        )
        self.messages.append({"role": "assistant", "content": response.content})
        text = "".join(block.text for block in response.content if block.type == "text")
        calls = [
            ToolCall(block.id, block.name, dict(block.input)) for block in response.content if block.type == "tool_use"
        ]
        return Reply(text, calls)

    def add_tool_results(self, outcomes: list[ToolOutcome]) -> None:
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": o.call.id, "content": o.text, "is_error": o.is_error}
                    for o in outcomes
                ],
            }
        )


class OpenAIProvider:
    """Chains turns with `previous_response_id`, so only new input is sent each time."""

    def __init__(self, model: str, system: str, tools: list[Tool]) -> None:
        self.label = f"openai/{model}"
        self.model = model
        self.system = system
        self.client = openai.AsyncOpenAI()
        self.tools: list[Any] = [
            {
                "type": "function",
                "name": t.name,
                "description": t.description or "",
                "parameters": t.input_schema,
                "strict": False,
            }
            for t in tools
        ]
        self.pending: list[Any] = []
        self.previous_id: str | None = None

    def add_user(self, text: str) -> None:
        self.pending.append({"role": "user", "content": text})

    async def complete(self) -> Reply:
        response = await self.client.responses.create(
            model=self.model,
            instructions=self.system,
            input=self.pending,
            tools=self.tools,
            previous_response_id=self.previous_id,
        )
        self.pending = []
        self.previous_id = response.id
        calls = [
            ToolCall(item.call_id, item.name, _arguments(item.arguments))
            for item in response.output
            if item.type == "function_call"
        ]
        return Reply(response.output_text, calls)

    def add_tool_results(self, outcomes: list[ToolOutcome]) -> None:
        self.pending += [{"type": "function_call_output", "call_id": o.call.id, "output": o.text} for o in outcomes]


class ChatCompletionsProvider:
    def __init__(self, model: str, system: str, tools: list[Tool], *, client: openai.AsyncOpenAI) -> None:
        self.label = f"openrouter/{model}"
        self.model = model
        self.client = client
        self.tools: list[Any] = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description or "", "parameters": t.input_schema},
            }
            for t in tools
        ]
        self.messages: list[Any] = [{"role": "system", "content": system}]

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    async def complete(self) -> Reply:
        response = await self.client.chat.completions.create(
            model=self.model, messages=self.messages, tools=self.tools, max_completion_tokens=MAX_TOKENS
        )
        message = response.choices[0].message
        self.messages.append(message.model_dump(exclude_none=True))
        calls = [
            ToolCall(call.id, call.function.name, _arguments(call.function.arguments))
            for call in message.tool_calls or []
            if call.type == "function"
        ]
        return Reply(message.content or "", calls)

    def add_tool_results(self, outcomes: list[ToolOutcome]) -> None:
        self.messages += [{"role": "tool", "tool_call_id": o.call.id, "content": o.text} for o in outcomes]
