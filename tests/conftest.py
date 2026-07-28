"""Test fixtures.

Tests drive the real MCP surface (`call_tool`) against a recording MIDI port, so
they cover tool registration and schema generation as well as the message bytes.
The only stand-in is the port itself — there's no way to assert on MIDI output
without one, and everything above it is the real code path.
"""

import mido
import pytest

from elektron_mcp.devices.digitakt import SPEC as DIGITAKT_SPEC
from elektron_mcp.devices.digitone import SPEC as DIGITONE_SPEC
from elektron_mcp.server import build_server

SPECS = {"digitakt": DIGITAKT_SPEC, "digitone": DIGITONE_SPEC}


class RecordingPort:
    """Stands in for an open MIDI port and keeps everything sent to it."""

    def __init__(self, name: str = "Mock Elektron") -> None:
        self.name = name
        self.messages: list[mido.Message] = []
        self.closed = False

    def send(self, message: mido.Message) -> None:
        self.messages.append(message)

    def iter_pending(self):
        return iter(())

    def close(self) -> None:
        self.closed = True

    # ------------------------------------------------------------- assertions

    def clear(self) -> None:
        self.messages.clear()

    @property
    def types(self) -> list[str]:
        return [m.type for m in self.messages]

    def of_type(self, message_type: str) -> list[mido.Message]:
        return [m for m in self.messages if m.type == message_type]

    def controls(self) -> list[tuple[int, int]]:
        """(cc number, value) for every control change sent."""
        return [(m.control, m.value) for m in self.of_type("control_change")]


class Harness:
    """A built server plus its recording port."""

    def __init__(self, device, port: RecordingPort) -> None:
        self.device = device
        self.port = port

    async def call(self, tool: str, **arguments):
        """Invoke a tool the way a client would, returning its text output."""
        result = await self.device.mcp.call_tool(tool, arguments)
        blocks = result[0] if isinstance(result, tuple) else result
        if isinstance(blocks, dict):
            return blocks
        return "\n".join(getattr(b, "text", "") for b in blocks)

    async def read(self, uri: str) -> str:
        contents = await self.device.mcp.read_resource(uri)
        return "\n".join(c.content for c in contents)

    async def tool_names(self) -> set[str]:
        return {t.name for t in await self.device.mcp.list_tools()}


def build(spec, tmp_path) -> Harness:
    device = build_server(spec, storage_root=tmp_path)
    port = RecordingPort()
    device.connection.output_port = port
    device.connection.input_port = port
    return Harness(device, port)


@pytest.fixture(params=sorted(SPECS), ids=sorted(SPECS))
def any_device(request, tmp_path) -> Harness:
    """Runs a test once per device, for behaviour the shared core provides to all."""
    return build(SPECS[request.param], tmp_path)


@pytest.fixture
def digitakt(tmp_path) -> Harness:
    return build(DIGITAKT_SPEC, tmp_path)


@pytest.fixture
def digitone(tmp_path) -> Harness:
    return build(DIGITONE_SPEC, tmp_path)
