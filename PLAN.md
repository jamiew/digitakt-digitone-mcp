# Digitakt MIDI MCP Server

## Status

**Digitakt 1 only** - focused on getting this working well before expanding.

Working MCP server with 44 tools for controlling an Elektron Digitakt via MIDI.

---

## Done

- [x] FastMCP server with 44 tools
- [x] Core MIDI: notes, CCs, NRPN, SysEx, sequences
- [x] Transport: start, stop, continue, song position
- [x] Trig/Step control: note, velocity, length per step
- [x] Named parameter control via `set_parameter` / `list_parameters`
- [x] Pattern playback with MIDI clock sync
- [x] Multi-channel MIDI patterns
- [x] Parameter automation: sweeps, envelopes
- [x] Pattern storage: save/load to JSON files
- [x] Automation presets: save/load
- [x] MIDI export: patterns and melodies to .mid files
- [x] MIDI recording: monitor and record input to .mid files
- [x] Linting and formatting (ruff)
- [x] CI workflow (GitHub Actions)
- [x] Unit tests with mocked MIDI (`test_fastmcp_migration.py`)
- [x] Hardware integration tests

---

## TODO

### High Priority

- [ ] **Compress tool descriptions** - Current docstrings are verbose, eating context tokens. Aim for <100 tokens/tool.
- [ ] **Add token counting test** - Measure actual tool schema tokens, fail if >6000 total
- [ ] **Improve error handling** - Better messages when MIDI port disconnected mid-session
- [ ] **Connection retry logic** - Auto-reconnect if Digitakt power-cycled

### Medium Priority

- [ ] **MCP Resources** - Add `midi://parameters` resource so LLM can fetch param list on demand instead of listing in tool descriptions
- [ ] **Consolidate playback tools** - 6 similar `play_pattern_*` tools could maybe be unified
- [ ] **Add `get_status` resource** - Connection state, current port, last message sent

### Low Priority / Future

- [ ] **Digitone MCP** - When needed, create separate repo, copy shared code
- [ ] **SysEx pattern dumps** - Read/write patterns directly from Digitakt memory
- [ ] **Kit parameter control** - Sample slot selection, sound locks

---

## Current Architecture

```
digitakt-midi-mcp/
├── server_fastmcp.py     # FastMCP server, 44 tools (~73KB)
├── parameter_map.py      # Digitakt CC/param definitions
├── nrpn_constants.py     # Digitakt NRPN definitions
├── digitakt_midi.py      # Entry point
├── tests/                # pytest + hardware tests
└── pyproject.toml
```

### Tools (44 total)

| Category | Count | Tools |
|----------|-------|-------|
| Core MIDI | 7 | `send_note`, `trigger_track`, `send_cc`, `send_nrpn`, `send_program_change`, `send_sysex`, `send_note_sequence` |
| Transport | 4 | `send_midi_start`, `send_midi_stop`, `send_midi_continue`, `send_song_position` |
| Trig/Step | 4 | `set_trig_note`, `set_trig_velocity`, `set_trig_length`, `reset_velocities` |
| Parameters | 2 | `list_parameters`, `set_parameter` |
| Playback | 6 | `play_with_clock`, `play_pattern_with_tracks`, `play_pattern_with_melody`, `play_pattern_with_loop`, `play_pattern_with_tracks_and_melody`, `play_pattern_with_multi_channel_midi` |
| Automation | 3 | `send_parameter_sweep`, `send_parameter_envelope`, `play_pattern_with_parameter_automation` |
| Patterns | 8 | `save_pattern`, `load_pattern`, `list_patterns`, `delete_pattern`, `update_pattern`, `edit_pattern_chords`, `edit_pattern_triggers`, `save_last_pattern` |
| Presets | 3 | `save_automation_preset`, `load_automation_preset`, `list_automation_presets` |
| Export | 3 | `export_pattern_to_midi`, `export_automation_to_midi`, `save_last_melody` |
| Recording | 4 | `monitor_midi_input`, `record_midi_input`, `list_midi_recordings`, `play_midi_file` |

---

## Token Usage

Each MCP tool adds to context sent with every request.

### Current Estimate: ~4,700 tokens

| Category | Tools | Est. Tokens |
|----------|-------|-------------|
| Core MIDI | 7 | ~700 |
| Transport | 4 | ~200 |
| Trig/Step | 4 | ~400 |
| Parameters | 2 | ~250 |
| Playback | 6 | ~900 |
| Automation | 3 | ~450 |
| Patterns | 8 | ~800 |
| Presets | 3 | ~300 |
| Export | 3 | ~300 |
| Recording | 4 | ~400 |

### Budget Guideline

Keep under 6,000 tokens per MCP for responsive performance.

---

## Multi-Device Strategy (Future)

When supporting multiple Elektron devices:

**Recommended: Separate MCPs per device**

```
digitakt-mcp     (~5K tokens)  # This repo
digitone-mcp     (~6K tokens)  # Future: separate repo
syntakt-mcp      (~6K tokens)  # Future: separate repo
```

User configures only what they need. Shared code is ~1,500 lines - copying is fine, no premature abstraction.

---

## Config Locations

| Data | Path |
|------|------|
| Patterns | `~/.mcp-config/digitakt/patterns/` |
| Automation presets | `~/.mcp-config/digitakt/presets/` |
| MIDI recordings | `~/.mcp-config/digitakt/recordings/` |

---

## Resources

- [Digitakt Manual](https://www.elektron.se/wp-content/uploads/2024/09/Digitakt_User_Manual_ENG_OS1.51_231108.pdf)
- [Elektron MIDI Guide](https://midi.guide/d/elektron/)
- [MCP Specification](https://modelcontextprotocol.io/)
