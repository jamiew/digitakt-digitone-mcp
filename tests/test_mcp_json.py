"""Launch every server in `.mcp.json` exactly as configured and drive it over stdio.

No MIDI device is needed: a missing port only logs a warning at startup.
"""

import json
import os
from importlib.metadata import version
from pathlib import Path

import pytest
from mcp import StdioServerParameters
from mcp.client import Client

ROOT = Path(__file__).resolve().parent.parent
SERVERS = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]


def expand(value: str) -> str:
    return value.replace("${CLAUDE_PROJECT_DIR:-.}", str(ROOT))


@pytest.mark.parametrize(("mode", "era"), [("legacy", "2025-11-25"), ("auto", "2026-07-28")])
@pytest.mark.parametrize("name", sorted(SERVERS))
async def test_mcp_json_server_starts_and_lists(name, mode, era, tmp_path):
    entry = SERVERS[name]
    params = StdioServerParameters(
        command=expand(entry["command"]),
        args=[expand(arg) for arg in entry.get("args", [])],
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", str(tmp_path))},
        cwd=tmp_path,
    )
    async with Client(params, mode=mode) as client:
        assert client.protocol_version == era
        assert client.server_info.version == version("digitakt-digitone-mcp")

        tools = (await client.list_tools()).tools
        assert tools
        for tool in tools:
            hints = tool.annotations
            assert hints is not None and hints.read_only_hint is not None, tool.name
            if not hints.read_only_hint:
                assert hints.destructive_hint is not None, tool.name

        await client.list_prompts()
        assert (await client.list_resources()).resources

        result = await client.call_tool("list_parameters", {})
        assert not result.is_error


@pytest.mark.parametrize("path", sorted(ROOT.glob("server.*.json")), ids=lambda path: path.name)
async def test_registry_entry_starts_its_device(path, tmp_path):
    """Run each MCP Registry entry's package command, as `uvx` would, from this checkout."""
    package = json.loads(path.read_text())["packages"][0]
    device = path.name.split(".")[1]
    args = [arg["value"] for arg in package.get("packageArguments", [])]
    params = StdioServerParameters(
        command="uv",
        args=["--directory", str(ROOT), "run", "--quiet", package["identifier"], *args],
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", str(tmp_path))},
        cwd=tmp_path,
    )
    async with Client(params) as client:
        assert client.server_info.name == f"{device}-midi"
        assert (await client.list_tools()).tools
