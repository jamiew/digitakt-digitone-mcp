# Elektron MIDI MCP — status and plan

## Where things stand

One repo, one package, **devices as data**. `build_server(spec)` produces a complete
FastMCP server from a `DeviceSpec`; each device ships its own console script so token
cost stays per-device. Digitakt and Digitone are supported; both are on the original
hardware, not the mk2 machines.

Green: `ruff check`, `ruff format --check`, `ty check`, 62 tests, wheel builds and
imports from an isolated install.

| | |
|---|---|
| Devices | Digitakt (44 tools, ~5.2k tokens), Digitone (43 tools, ~5.1k tokens) |
| Entry points | `digitakt-mcp`, `digitone-mcp` |
| Python | 3.11–3.13 |
| Tests | 62, no hardware required |

## Architecture

```
src/elektron_mcp/
  device.py      DeviceSpec, Parameter, parse_parameters
  midi.py        MidiConnection — ports, sending, logging
  clock.py       Event + play(); the single clock loop
  storage.py     ~/.mcp-config/<slug>/{patterns,presets,recordings}
  midifile.py    .mid writing
  server.py      build_server(spec) + all 35 shared tools
  devices/
    digitakt.py         SPEC + 9 device tools
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
- [x] CI: lint + format + types, tests on 3.11/3.12/3.13, wheel build and import check
- [x] Pin `mcp>=1.26.0,<2` — see below
- [x] `midi://<device>/parameters` resource so parameter names needn't live in tool text

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

- [ ] **Verify on real hardware.** The refactor is covered by unit tests but no Digitakt
      or Digitone has been touched since. Highest-risk areas: clock timing under the
      unified `clock.play()`, the looping-event modulo path, and `start_at_beat`.
- [ ] **Generate parameter maps from [`pencilresearch/midi`](https://github.com/pencilresearch/midi)**
      instead of maintaining them by hand. Their CSVs cover the whole Elektron line with
      `cc_msb`/`cc_lsb`/`nrpn_msb`/`nrpn_lsb`/min/max/default plus an `orientation` field
      (0-based vs centered) that hand-rolled maps usually get wrong. This is the single
      highest-leverage change available: it would fix 14-bit CC pairs, add value ranges
      we currently lack, and make Digitakt II / Syntakt / Analog Rytm nearly free.
- [ ] **Cross-check the existing maps** against that database before trusting them.

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
- [ ] **`mcp` 2.x migration.** 2.0 dropped `mcp.server.fastmcp` for `mcp.server.mcpserver`.
      Pinned to `<2` for now; this is a real rewrite of the registration layer.
- [ ] **Publish to PyPI** so it's `uvx digitakt-mcp` with no clone.
- [ ] Kit / sound-lock parameters, sample slot selection.

## Notes on the ecosystem

The Elektron-MCP space is close to empty. A survey found only three public MCP servers
touching Elektron gear, one of which is this project's upstream. The useful prior art is
in parameter *data* and architecture, not in servers to reuse — hence the plan above.
Full list of what was surveyed is in the README's credits section.
