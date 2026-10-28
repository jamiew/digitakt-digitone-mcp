# Elektron MIDI MCP — status and plan

## Where things stand

One repo, one package, **devices as data**. `build_server(spec)` produces a complete
FastMCP server from a `DeviceSpec`; each device ships its own console script so token
cost stays per-device. Digitakt and Digitone are supported; both are on the original
hardware, not the mk2 machines.

Green: `ruff check`, `ruff format --check`, `ty check`, 95 tests, wheel builds and
imports from an isolated install. Runs on mcp 2.3 (`MCPServer`), protocol 2026-07-28.

| | |
|---|---|
| Devices | Digitakt (50 tools, ~7.0k tokens), Digitone (44 tools, ~6.3k tokens) |
| Entry points | `digitakt-mcp`, `digitone-mcp`, both in `.mcp.json` |
| Python | 3.11–3.14 |
| Tests | 95, no hardware required; plus `harness/` for live LLM runs |

## Architecture

```
src/elektron_mcp/
  device.py      DeviceSpec, Parameter, parse_parameters
  midi.py        MidiConnection — ports, sending, logging
  clock.py       Event + play(); the single clock loop
  storage.py     ~/.mcp-config/<slug>/{patterns,presets,recordings}
  midifile.py    .mid writing
  server.py      build_server(spec) + all 37 shared tools
  devices/
    digitakt.py         SPEC + 7 device tools
    digitone.py         SPEC + 6 FM tools
    *_params.py         parameter tables (data)
    *_cc.py             CC/NRPN constants (data)
```

The key move was replacing module-level `output_port` globals with a `MidiConnection`
held on a `DeviceServer`. Tools are closures over that object, so one implementation
serves every device. Before this, the two servers shared **1,190 identical lines** —
roughly 76% of the Digitone server was the Digitakt server with names swapped.

**Adding a device**: write a `DeviceSpec` (port name, track count, parameter table,
optional `register_tools` hook) and a console script entry. A Digitakt II is mostly a
new parameter map.

## Done

- [x] Collapse the two duplicated servers into a shared core + device specs
- [x] `src/` layout — top-level modules named `shared`, `server`, `parameter_map` were
      publishing into the global namespace from the wheel
- [x] Delete `server.py` (4,329-line pre-FastMCP server behind `DIGITAKT_USE_LEGACY`)
      and `play_hiphop.py` — they held all 18 lint errors and kept CI red
- [x] Move the 10 hardware scripts out of `tests/` into `scripts/hardware/`, so a bare
      `pytest` collects only real tests
- [x] Typed `Parameter` table with validation at import (`parse_parameters`)
- [x] Type checking with `ty`, plus `py.typed`
- [x] Rewrite tests against the real MCP surface (`call_tool`), parameterized over devices
- [x] CI: lint + format + types, tests on 3.11–3.14, wheel build and import check
- [x] Pin `mcp>=1.26.0,<2` — superseded by the 2.x migration below
- [x] `midi://<device>/parameters` resource so parameter names needn't live in tool text
- [x] **mcp 2.x migration** to `MCPServer` (see below for what it changed)
- [x] `.mcp.json` for Claude Code, and a live harness (`python -m harness`) that drives
      either server with Anthropic, OpenAI or OpenRouter, as chat, a scenario suite, or
      single tool calls. `--dry-run` captures MIDI in-process for no-hardware runs.

### MCP protocol audit (Oct 2026)

| Feature | Before | Now |
|---|---|---|
| Tool parameter docs | **Dropped.** `Annotated[int, "text"]` isn't read by pydantic, so no parameter had a description; row formats like `[beat, note, velocity, duration]` never reached the model | `Field(description=..., ge=, le=)`, enforced by a schema test |
| Array schemas | Bare `list` → `{"type": "array"}` with no items, which OpenAI rejects | Typed rows (`list[list[number]]`) |
| Tool errors | Raised `ValueError` etc. On mcp 2.x these reach the client as just "Error executing tool X" | `ToolError`, so the model sees "Unknown parameter 'x'. Use list_parameters…" |
| Output schema | Auto `{"result": string}` on every tool, duplicating each result as structured content | Off (`structured_output=False`); results are text |
| Tool annotations | None | Every tool: read-only / destructive / idempotent / open-world hints |
| Server identity | Name only | `title`, `version`, and `instructions` (channels, beats, where parameters live) |
| Progress | None | Clock-driven tools report each bar |
| Cancellation | Device left mid-pattern | Cancelled playback sends MIDI Stop |
| Resources | 3, no mime types | Same 3, JSON ones marked `application/json` |
| Prompts, completions, elicitation, sampling, logging | Unused | Still unused. Sampling, roots and logging are deprecated in the 2026-07-28 spec; elicitation could confirm `delete_pattern` but annotations already let clients ask |

Also fixed while migrating: `play_midi_file` used `MidiFile.play()`, which blocks the
event loop for the whole file; sync tools now run on worker threads, so `MidiConnection`
locks around sends to keep NRPN sequences whole; an event before pulse 0 used to stall
every later event in `clock.play`.

### Bugs found and fixed during the refactor

- **`set_parameter` ignored declared ranges.** It read `info["min"]`/`info["max"]`, but
  the tables store `range: (min, max)`. Both lookups missed, so it fell back to 0–127 and
  happily sent out-of-range values. Only Digitone's `fm_algorithm` (0–7) is actually
  narrower than 0–127, so this was latent on the Digitakt.
- **`set_parameter` rejected every NRPN parameter** with "does not have a CC mapping" —
  that's 34 of 67 Digitakt and 47 of 100 Digitone parameters unreachable by name.
- **Dropped note-offs.** `asyncio.create_task` results weren't referenced, and asyncio
  only holds weak references to tasks, so a scheduled note-off could be garbage-collected
  before firing — a stuck note. Now tracked in a set until done.
- **`set_operator_envelope` read its arguments via `locals().get()` inside a loop.**
  Worked, but silently depended on parameter names matching dict keys.
- **`mcp` was unpinned across a major version.** The lockfile held 1.26.0 so local dev was
  fine, but a fresh install resolved 2.0.0, where `mcp.server.fastmcp` no longer exists —
  every entry point would have failed on a clean machine.

### Inherited Digitakt II code, removed

`scripts/hardware/verify_cc_mappings.py` claimed to verify this repo's CC/NRPN table, but
its expected values were **Digitakt II**: AMP Volume CC 89 / Pan CC 90, against the mk1's
CC 7 / CC 10, plus amp sustain and release stages and a chorus send the original Digitakt
does not have. It could never pass here. This repo forked from
[`feamster/digitakt-midi-mcp`](https://github.com/feamster/digitakt-midi-mcp), which
targets the II — so the script was verifying the wrong machine all along. Our constants
are the ones that are right for a mk1; the script is gone (recoverable from git history if
a Digitakt II spec ever lands, where its expectations become correct).

`scripts/hardware/test_filter_sweeps.py` was also removed: it drove the deleted legacy
`server.py` through `server.call_tool()` and can't be salvaged without a rewrite.

## TODO

### High priority

- [ ] **Verify on real hardware.** Partly done on a Digitakt over USB (Oct 2026): stdio
      server connects, `trigger_track` and a 2-bar `play_pattern_with_tracks` play, progress
      arrives per bar, and cancelling `play_with_clock` mid-run sends Stop. Not yet heard:
      the looping-event modulo path, `start_at_beat`, and anything on a Digitone.
- [ ] **Generate parameter maps from [`pencilresearch/midi`](https://github.com/pencilresearch/midi)**
      instead of maintaining them by hand. Their CSVs cover the whole Elektron line with
      `cc_msb`/`cc_lsb`/`nrpn_msb`/`nrpn_lsb`/min/max/default plus an `orientation` field
      (0-based vs centered) that hand-rolled maps usually get wrong. This is the single
      highest-leverage change available: it would fix 14-bit CC pairs, add value ranges
      we currently lack, and make Digitakt II / Syntakt / Analog Rytm nearly free.
- [ ] **Cross-check the existing maps** against that database before trusting them.
- [x] **Storage bridge v1, on `elektroid-cli`.** `elektroid.py` wraps the CLI and parses
      its output, `drive.py` has the tools, `kit.py` guesses drum roles from names.
      Tools: `list_drive`, `list_sample_slots`, `load_sample`, `upload_samples`,
      `bootstrap_kit`, `list_sounds`. There's also a `midi://digitakt/kit` resource, plus
      prompts `new_kit`, `load_cipher_pack` and (Digitone) `new_sounds`.

      Tried on a Digitakt (OS 1.52A, Oct 2026) with the MCP server holding the same MIDI
      port: listing works, and `bootstrap_kit` put a kick, snare, break, hats and crash on
      tracks, which then played. Afterwards every track was set back to its original slot.
      Found on the way:
      - **The AUTO channel wins.** A sample-slot CC on channel 1 moved the *active* track
        (4), not track 1, because channel 1 is also this unit's AUTO channel. The tools now
        read the tracks back and warn when a track didn't change.
      - Each `harness call` starts a new server. Launching several back to back once failed
        with a CoreMIDI "error creating client" (-304) from rtmidi. It was transient.
      - Not yet tried on hardware: `upload_samples`, and `load_sample` with a local or
        not-yet-loaded file. Both write to the +Drive (the latter via `/incoming`).
- [ ] **Native SysEx storage backend.** Elektron's file protocol has a "load this +Drive
      path into slot N, for track T" request (`0x19` in elektroid's `elektron.c`). It would
      remove the `/incoming` copies, and it addresses the track directly, which avoids the
      AUTO channel problem. It goes behind the same `Elektroid` methods, and the
      `elektroid-cli` dependency then becomes optional.
- [ ] **More MCP surface for storage:** a `midi://digitakt/drive/{path}` resource template,
      and completions for +Drive paths and slot numbers in prompt arguments. Leave out:
      elicitation (annotations already let clients ask), sampling and roots (deprecated
      in the 2026-07-28 spec), and audio blobs in resources (models can't listen).

### Medium

- [ ] **Display-value ↔ MIDI-value scaling.** Tools currently speak raw 0–127. Elektron
      screens show ratios (0.25–16.0), dB, ms, and enum names.
      [`mcp-midi-control`](https://github.com/TheAndrewStaker/mcp-midi-control) makes a
      good case that tools should take and return what's on the front panel.
      `zerubeus/elektron-mcp` has the only public Digitone scaling tables.
- [ ] **Consolidate the playback tools.** Five `play_*` tools now share one engine and
      differ mostly in argument shape; they could likely collapse to two, cutting ~1k
      tokens per server.
- [ ] **Connection resilience.** Reconnect when the device is power-cycled instead of
      failing until restart.
- [ ] **Token budget test** — assert the tool schema stays under ~6k tokens per server.

### Low / future

- [ ] **Digitakt II and Digitone II** as additional specs, once maps are generated.
- [ ] **SysEx pattern dumps** — read/write patterns from device memory.
      [`mzero/elk-herd`](https://github.com/mzero/elk-herd) (BSD-2) documents the struct
      layouts per OS version and is the most authoritative public source; its author was
      given Elektron's actual headers. Covers Digitakt and Digitakt II, not Digitone.
- [ ] **Chorus map disagreement on the Digitone.** `set_chorus` sends CCs from
      `ChorusCC`, while `set_parameter("chorus_mix")` sends NRPNs from `ChorusParams`. At
      most one is right for the mk1; check on hardware.
- [ ] **Run `python -m harness digitone test` on a Digitone.** The Digitone scenarios have
      only run in `--dry-run`.
- [ ] **Publish to PyPI** so it's `uvx digitakt-mcp` with no clone.
- [ ] Kit / sound-lock parameters, sample slot selection.

## Notes on the ecosystem

The Elektron-MCP space is close to empty. A survey found only three public MCP servers
touching Elektron gear, one of which is this project's upstream. The useful prior art is
in parameter *data* and architecture, not in servers to reuse — hence the plan above.
Full list of what was surveyed is in the README's credits section.
