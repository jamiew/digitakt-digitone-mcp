"""Connecting to a server and running the model's tool-use loop against it."""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mido
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent, Tool

from elektron_mcp.devices import DEVICES
from elektron_mcp.elektroid import Elektroid, ElektroidError
from elektron_mcp.server import build_server
from harness.providers import Provider, ToolCall, ToolOutcome

REPO = Path(__file__).resolve().parent.parent
MAX_STEPS = 12
"""Model round trips allowed per prompt before giving up."""

_TTY = sys.stdout.isatty()


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


class CapturePort(mido.ports.BaseOutput):
    """Stands in for the device in --dry-run. The server logs each message it sends.

    Output only: there's no device to hear from, so the input tools report "not connected".
    """

    def __init__(self) -> None:
        self.messages: list[mido.Message] = []
        super().__init__(name="dry-run")

    def _send(self, msg: mido.Message) -> None:
        self.messages.append(msg)


def server_params(device: str) -> StdioServerParameters:
    """Launch the server exactly as Claude Code would, from .mcp.json."""
    entry = json.loads((REPO / ".mcp.json").read_text())["mcpServers"][device]
    env = entry.get("env")
    return StdioServerParameters(command=entry["command"], args=entry.get("args", []), env=env, cwd=REPO)


@dataclass
class Session:
    client: Client
    device: str
    tools: list[Tool]
    dry_run: bool

    @property
    def system_prompt(self) -> str:
        target = (
            "This is a dry run: MIDI is captured instead of reaching hardware."
            if self.dry_run
            else "The hardware is connected; every tool call makes real sound."
        )
        return (
            f"You operate an Elektron {DEVICES[self.device].display_name} through MCP tools. {target}\n"
            f"{self.client.instructions or ''}\n"
            "Do exactly what's asked with as few tool calls as possible. Don't add playback that wasn't requested. "
            "Answer in one or two short sentences."
        )

    async def call(self, call: ToolCall) -> ToolOutcome:
        async def on_progress(progress: float, total: float | None, message: str | None) -> None:
            print(paint(f"    … {message or progress}", "2"))

        result = await self.client.call_tool(call.name, call.arguments, progress_callback=on_progress)
        text = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
        return ToolOutcome(call, text, bool(result.is_error), {**self.defaults(call.name), **call.arguments})

    def defaults(self, tool_name: str) -> dict[str, Any]:
        tool = next((t for t in self.tools if t.name == tool_name), None)
        properties = tool.input_schema.get("properties", {}) if tool else {}
        return {name: prop["default"] for name, prop in properties.items() if "default" in prop}


async def _no_storage(args: list[str], timeout: float) -> str:
    raise ElektroidError("The +Drive and sample slots aren't available in --dry-run.")


@asynccontextmanager
async def connect(device: str, *, dry_run: bool) -> AsyncGenerator[Session]:
    if not dry_run:
        async with Client(server_params(device)) as client:
            yield Session(client, device, (await client.list_tools()).tools, dry_run=False)
        return

    # In-process server against a capture port, with patterns etc. in a throwaway dir.
    with tempfile.TemporaryDirectory() as storage:
        server = build_server(DEVICES[device], storage_root=Path(storage))
        port = CapturePort()
        server.connection.output_port = port
        # A dry run must not touch the real device, and elektroid would.
        server.elektroid = Elektroid(server.spec.port_name, runner=_no_storage)
        async with Client(server.mcp) as client:
            yield Session(client, device, (await client.list_tools()).tools, dry_run=True)
        print(paint(f"(dry run captured {len(port.messages)} MIDI messages)", "2"))


def describe(call: ToolCall) -> str:
    args = ", ".join(f"{k}={json.dumps(v)}" for k, v in call.arguments.items())
    return f"{call.name}({args})"


async def run_prompt(session: Session, provider: Provider, prompt: str) -> tuple[str, list[ToolOutcome]]:
    """Send one user message and let the model call tools until it answers. Returns (answer, calls)."""
    provider.add_user(prompt)
    outcomes: list[ToolOutcome] = []
    answer = ""

    for _ in range(MAX_STEPS):
        reply = await provider.complete()
        answer = reply.text or answer
        if not reply.tool_calls:
            return answer, outcomes

        if reply.text:
            print(paint(f"  {reply.text.strip()}", "2"))
        batch = []
        for call in reply.tool_calls:
            print(paint(f"  → {describe(call)}", "36"))
            outcome = await session.call(call)
            print(
                paint(
                    f"  {'✗' if outcome.is_error else '←'} {_first_line(outcome.text)}",
                    "31" if outcome.is_error else "2",
                )
            )
            batch.append(outcome)
        outcomes += batch
        provider.add_tool_results(batch)

    return f"(stopped after {MAX_STEPS} model steps)", outcomes


def _first_line(text: str, limit: int = 160) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


def parse_value(raw: str) -> Any:
    """`call` arguments: JSON when it parses (numbers, lists, true), else a plain string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw
