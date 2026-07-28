# Elektron MIDI MCP

MCP servers for controlling Elektron Digitakt and Digitone (both **original**, not the II
models) via MIDI. One package, one shared server core, one `DeviceSpec` per device.

## Quick Reference

- **Entry points**: `uv run digitakt-mcp`, `uv run digitone-mcp`
- **Tests**: `uv run pytest` (62 tests, no hardware needed)
- **Checks**: `uv run ruff check . && uv run ruff format --check . && uv run ty check`
- **Hardware scripts**: `scripts/hardware/` — manual, need a real device, not collected by pytest

## Key Files

| File | Purpose |
|------|---------|
| `src/elektron_mcp/server.py` | `build_server(spec)` + the 35 shared tools |
| `src/elektron_mcp/device.py` | `DeviceSpec`, typed `Parameter`, `parse_parameters` |
| `src/elektron_mcp/midi.py` | `MidiConnection` — ports, sending, logging |
| `src/elektron_mcp/clock.py` | `Event` + `play()`; the one clock loop |
| `src/elektron_mcp/devices/digitakt.py` | Digitakt spec + its 9 device-specific tools |
| `src/elektron_mcp/devices/digitone.py` | Digitone spec + its 6 FM tools |
| `src/elektron_mcp/devices/*_params.py` | Parameter tables (data) |
| `src/elektron_mcp/devices/*_cc.py` | CC/NRPN constants (data) |
| `PLAN.md` | Status, TODO, architecture notes |

## Conventions

- **Devices are data.** Adding a device = one `DeviceSpec` + entry point, never a new
  server. Don't add device-specific branching to `server.py`; use the `register_tools` hook.
- **No module-level MIDI globals.** Everything goes through `DeviceServer.connection`.
  Globals are what forced the original two servers to be copy-pasted.
- **Tools raise on failure** rather than returning `"Error: ..."` strings — FastMCP turns
  exceptions into proper MCP tool errors.
- `mcp` is pinned `<2`: 2.x dropped `mcp.server.fastmcp`.

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

## Creator's Hardware Setup & MIDI Mapping

### Digitakt Audio Tracks (1-8) → Channels 1-8

| Track | Channel | Sound |
|-------|---------|-------|
| 1 | 1 | Kick |
| 2 | 2 | Snare |
| 3 | 3 | Tom |
| 4 | 4 | Clap |
| 5 | 5 | Cowbell |
| 6 | 6 | Closed Hat |
| 7 | 7 | Open Hat |
| 8 | 8 | Cymbal |

### Digitakt MIDI Tracks (A-H / 9-16) → Digitone

Digitakt Settings > MIDI > Tracks A-H channels = 9-16

The Digitone has 4 synth tracks. Each Digitone track receives from **two** Digitakt MIDI tracks (for pattern alternation):

| Digitakt Tracks | Channel | Digitone Track |
|-----------------|---------|----------------|
| 9, 10 | 9, 10 | Track 1 (chords/keys) |
| 11, 12 | 11, 12 | Track 2 (bass) |
| 13, 14 | 13, 14 | Track 3 (lead) |
| 15, 16 | 15, 16 | Track 4 |

**Why pairs?** Using two Digitakt tracks per Digitone track allows alternating patterns on the Digitakt while sequencing the same Digitone instrument.

### MIDI Signal Flow

```
Computer (USB) → Digitakt → Digitone (via MIDI DIN)
                    │
                    ├── Tracks 1-8: Internal samples (drums)
                    └── Tracks 9-16: MIDI out to Digitone (synths)
```

### Channel Summary for Programming

- **Drums**: Channels 1-8 (notes 0-7 trigger tracks 1-8)
- **Digitone chords**: Channel 9 (Digitakt track 9)
- **Digitone bass**: Channel 11 (Digitakt track 11)
- **Digitone lead**: Channel 13 (Digitakt track 13)
- **Digitone track 4**: Channel 15 (Digitakt track 15)
