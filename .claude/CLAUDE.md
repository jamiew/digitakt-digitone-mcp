# Digitakt MIDI MCP

MCP server for controlling Elektron Digitakt (original, not II) via MIDI.

## Quick Reference

- **Main server**: `server_fastmcp.py` (44 tools, FastMCP)
- **Entry point**: `uv run digitakt-midi`
- **Tests**: `uv run pytest` or `uv run pytest tests/test_fastmcp_migration.py` for unit tests only
- **Lint**: `uv run ruff check . && uv run ruff format --check .`

## Key Files

| File | Purpose |
|------|---------|
| `server_fastmcp.py` | All 44 MCP tools |
| `parameter_map.py` | Named parameter → CC/NRPN mapping |
| `nrpn_constants.py` | NRPN MSB/LSB constants |
| `PLAN.md` | TODO list and architecture notes |

## Digitakt MIDI Basics

- **Tracks 1-8**: Audio tracks, triggered by notes 0-7 on their respective MIDI channels
- **Tracks 9-16**: MIDI tracks (send MIDI out, not relevant for this MCP)
- **1 LFO** per track (not 3 like Digitakt II)
- **No Chorus** effect (Digitakt II only)

### Channel Routing

Each track listens on its own MIDI channel (1-8) when configured correctly:
- Track 1 → Channel 1
- Track 2 → Channel 2
- etc.

### Common CCs

| Parameter | CC |
|-----------|-----|
| Filter Cutoff | 74 |
| Filter Resonance | 75 |
| Volume | 7 |
| Pan | 10 |
| Delay Send | 82 |
| Reverb Send | 83 |

## Testing

Hardware tests require connected Digitakt. Unit tests mock MIDI:

```bash
# Unit tests only (no hardware)
uv run pytest tests/test_fastmcp_migration.py -v

# All tests (needs Digitakt connected)
uv run pytest
```

## Data Storage

All user data in `~/.mcp-config/digitakt/`:
- `patterns/` - Saved pattern JSON files
- `presets/` - Automation preset JSON files
- `recordings/` - Recorded MIDI files

## Token Budget

This MCP uses ~4,700 tokens for tool schemas. Keep under 6,000 for good performance. When compressing docstrings, aim for <100 tokens per tool.

---

