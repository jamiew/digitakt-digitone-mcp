# Digitone MCP Research

Research for building a Digitone MIDI MCP server, adapted from the existing Digitakt MCP.

## Digitone vs Digitakt: Key Differences

| Feature | Digitakt | Digitone |
|---------|----------|----------|
| Engine | Sample player | 4-operator FM synth |
| Audio tracks | 8 | 4 synth tracks |
| MIDI tracks | 8 | 4 MIDI tracks |
| LFOs per track | 1 | 2 |
| Effects | Delay, Reverb | Chorus, Delay, Reverb |
| Voices | 8 | 8 (shared across 4 tracks) |
| Param pages | SRC, FLT, AMP, LFO | SYN1, SYN2, FLT, AMP, LFO, FX |
| Note input | Notes 0-7 trigger tracks | Full chromatic per track |
| Unique feature | Sample manipulation | FM algorithms, operator envelopes |

## Channel Configuration

| Entity | Default Channel | Purpose |
|--------|----------------|---------|
| Synth Track 1 | 1 | FM synth voice 1 |
| Synth Track 2 | 2 | FM synth voice 2 |
| Synth Track 3 | 3 | FM synth voice 3 |
| Synth Track 4 | 4 | FM synth voice 4 |
| MIDI Track 1-4 | 5-8 (configurable) | External MIDI out |
| FX Channel | 9 (configurable) | Global effects control |
| Auto Channel | 10 (default) | Controls active track |

Settings: `GLOBAL SETTINGS > MIDI CONFIG > CHANNELS`

## FM Synthesis Architecture

### Operators

4 operators: **C**, **A**, **B1**, **B2**

- **C**: Always a carrier. Limited to integer ratios (carries the base note).
- **A**: Can be carrier or modulator. Extended ratio values for inharmonic sounds.
- **B1/B2**: Controlled together by the "B" ratio knob. Share one envelope. Can be carrier or modulator.

### 8 Algorithms

Each algorithm routes the 4 operators differently and outputs to **X** and **Y** buses. The **Mix** knob crossfades between X and Y.

Four routing shapes:
1. **Stack**: Cascade (e.g., B2→B1→C). Deep, complex modulation chains.
2. **Branch**: Multiple modulators into one carrier. Blended timbral effects.
3. **Root**: One modulator feeds multiple carriers. Layered variations.
4. **Carrier-only**: Direct output, no FM modulation. Clean/organ tones.

### Key FM Parameters (SYN1 page)

| Parameter | Effect |
|-----------|--------|
| Algorithm | Operator routing (1-8) |
| Ratio C | Carrier pitch ratio (integers) |
| Ratio A | Modulator pitch ratio (extended values) |
| Ratio B | B1/B2 pitch ratio |
| Harmonics | Harmonic content |
| Detune | Fine pitch offset |
| Feedback | Self-modulation (adds harmonics/noise) |
| Mix | X/Y crossfader between algorithm outputs |

### Operator Envelopes (SYN2 page)

Two operator envelopes: one for **A**, one for **B** (controls both B1/B2).

Each has: Attack, Decay, End level, Level, Delay, Trig mode, Env Reset.

The "End level" is unique to FM - it sets the amplitude after decay, useful because you often want sustained modulation rather than silence.

### Sound Design by Ratio

| M:C Ratio | Sound Character |
|-----------|----------------|
| 1:1 | Sawtooth-like (all harmonics) |
| 2:1 | Square-like (odd harmonics, clarinet) |
| 3:1 | Narrow pulse |
| 4:1 | Oboe-like |
| Non-integer | Metallic, bell-like, inharmonic |

---

## Complete MIDI CC/NRPN Map

Source: [midi.guide/d/elektron/digitone](https://midi.guide/d/elektron/digitone/)

### Track Parameters

| CC MSB | Parameter | NRPN MSB | NRPN LSB |
|--------|-----------|----------|----------|
| 94 | Mute | 1 | 101 |
| 95 | Track level | 1 | 100 |

### Trig Parameters

| CC MSB | Parameter | NRPN MSB | NRPN LSB |
|--------|-----------|----------|----------|
| 3 | Root note | 3 | 0 |
| 4 | Velocity | 3 | 1 |
| 5 | Length | 3 | 2 |
| 13 | Filter trig | 3 | 5 |
| 14 | LFO trig | 3 | 6 |
| 15 | Portamento time | 3 | 7 |
| 16 | Portamento on | 3 | 8 |

### FM Parameters - SYN1

| CC MSB | CC LSB | Parameter | NRPN MSB | NRPN LSB |
|--------|--------|-----------|----------|----------|
| 90 | — | Algorithm | 1 | 72 |
| 91 | — | Ratio C | 1 | 73 |
| 92 | — | Ratio A | 1 | 74 |
| 16 | 48 | Ratio B | 1 | 75 |
| 17 | 49 | Harmonics | 1 | 76 |
| 18 | 50 | Detune | 1 | 77 |
| 19 | 51 | Feedback | 1 | 78 |
| 20 | 52 | Mix | 1 | 79 |
| — | — | Ratio C offset | 1 | 95 |
| — | — | Ratio A offset | 1 | 96 |
| — | — | Ratio B1 offset | 1 | 97 |
| — | — | Ratio B2 offset | 1 | 98 |

**Note:** Ratio offsets are NRPN-only (no CC). They have ~2000 values, requiring 14-bit NRPN.

### FM Parameters - SYN2 (Operator Envelopes)

| CC MSB | Parameter | NRPN MSB | NRPN LSB |
|--------|-----------|----------|----------|
| 75 | A env attack | 1 | 80 |
| 76 | A env decay | 1 | 81 |
| 77 | A env end | 1 | 82 |
| 78 | A level | 1 | 83 |
| 79 | B env attack | 1 | 84 |
| 80 | B env decay | 1 | 85 |
| 81 | B env end | 1 | 86 |
| 82 | B level | 1 | 87 |
| 83 | A delay | 1 | 88 |
| 84 | A trig | 1 | 89 |
| 85 | A env reset | 1 | 90 |
| 86 | B delay | 1 | 91 |
| 87 | B trig | 1 | 92 |
| 88 | B env reset | 1 | 93 |
| 89 | Phase reset | 1 | 94 |

### Filter Parameters

| CC MSB | CC LSB | Parameter | NRPN MSB | NRPN LSB |
|--------|--------|-----------|----------|----------|
| 23 | 55 | Frequency | 1 | 20 |
| 24 | 56 | Resonance | 1 | 21 |
| 74 | — | Type | 1 | 22 |
| 70 | — | Env attack | 1 | 16 |
| 71 | — | Env decay | 1 | 17 |
| 72 | — | Env sustain | 1 | 18 |
| 73 | — | Env release | 1 | 19 |
| 25 | 57 | Env depth | 1 | 23 |
| 43 | — | Env delay | 1 | 66 |
| 26 | 58 | Base | 1 | 24 |
| 27 | 59 | Width | 1 | 25 |

### Amp Parameters

| CC MSB | CC LSB | Parameter | NRPN MSB | NRPN LSB |
|--------|--------|-----------|----------|----------|
| 104 | — | Attack | 1 | 32 |
| 105 | — | Decay | 1 | 33 |
| 106 | — | Sustain | 1 | 34 |
| 107 | — | Release | 1 | 35 |
| 9 | 41 | Drive | 1 | 36 |
| 10 | 42 | Pan | 1 | 37 |
| 7 | 39 | Volume | 1 | 38 |
| 12 | 44 | Chorus send | 1 | 41 |
| 13 | 45 | Delay send | 1 | 40 |
| 14 | 46 | Reverb send | 1 | 39 |
| 102 | — | Amp env reset | 1 | 42 |

### LFO 1 Parameters

| CC MSB | CC LSB | Parameter | NRPN MSB | NRPN LSB |
|--------|--------|-----------|----------|----------|
| 28 | 60 | Speed | 1 | 48 |
| 108 | — | Multiplier | 1 | 49 |
| 109 | — | Fade in/out | 1 | 50 |
| 110 | — | Destination | 1 | 51 |
| 111 | — | Waveform | 1 | 52 |
| 112 | — | Start phase | 1 | 53 |
| 113 | — | Trig mode | 1 | 54 |
| 29 | 61 | Depth | 1 | 55 |

### LFO 2 Parameters

| CC MSB | CC LSB | Parameter | NRPN MSB | NRPN LSB |
|--------|--------|-----------|----------|----------|
| 30 | 62 | Speed | 1 | 57 |
| 114 | — | Multiplier | 1 | 58 |
| 115 | — | Fade in/out | 1 | 59 |
| 116 | — | Destination | 1 | 60 |
| 117 | — | Waveform | 1 | 61 |
| 118 | — | Start phase | 1 | 62 |
| 119 | — | Trig mode | 1 | 63 |
| 31 | 63 | Depth | 1 | 64 |

### Chorus Parameters (FX channel)

| CC MSB | CC LSB | Parameter | NRPN MSB | NRPN LSB |
|--------|--------|-----------|----------|----------|
| 3 | 35 | Depth | 2 | 0 |
| 9 | 41 | Speed | 2 | 1 |
| 70 | — | High-pass | 2 | 2 |
| 71 | — | Width | 2 | 3 |
| 12 | 44 | Delay send | 2 | 4 |
| 13 | 45 | Reverb send | 2 | 5 |
| 14 | — | Mix volume | 2 | 6 |

### Delay Parameters (FX channel)

| CC MSB | CC LSB | Parameter | NRPN MSB | NRPN LSB |
|--------|--------|-----------|----------|----------|
| 15 | 47 | Time | 2 | 10 |
| 16 | 48 | Pingpong | 2 | 11 |
| 17 | 49 | Stereo width | 2 | 12 |
| 18 | 50 | Feedback | 2 | 13 |
| 72 | — | HPF | 2 | 14 |
| 73 | — | LPF | 2 | 15 |
| 19 | 51 | Reverb send | 2 | 16 |
| 20 | — | Mix volume | 2 | 17 |

### Reverb Parameters (FX channel)

| CC MSB | CC LSB | Parameter | NRPN MSB | NRPN LSB |
|--------|--------|-----------|----------|----------|
| 21 | 53 | Predelay | 2 | 20 |
| 74 | — | Decay | 2 | 21 |
| 75 | — | Shelving freq | 2 | 22 |
| 22 | 54 | Shelving gain | 2 | 23 |
| 76 | — | HPF | 2 | 24 |
| 77 | — | LPF | 2 | 25 |
| 23 | — | Mix volume | 2 | 26 |

### Master Parameters (FX channel)

| CC MSB | CC LSB | Parameter | NRPN MSB | NRPN LSB |
|--------|--------|-----------|----------|----------|
| 29 | 61 | Master overdrive | 2 | 37 |
| 95 | — | Pattern volume | 2 | 38 |
| 24 | 56 | Input L volume | 2 | 30 |
| 25 | 57 | Input R volume | 2 | 32 |
| 78 | — | Pan L | 2 | 31 |
| 79 | — | Pan R | 2 | 33 |
| 26 | 58 | Chorus send L | 2 | 34 |
| 30 | 62 | Chorus send R | 2 | 102 |
| 27 | 59 | Delay send L | 2 | 35 |
| 31 | 63 | Delay send R | 2 | 103 |
| 28 | 60 | Reverb send L | 2 | 36 |
| 82 | 32 | Reverb send R | 2 | 104 |

### Other

| CC MSB | Parameter | NRPN MSB | NRPN LSB |
|--------|-----------|----------|----------|
| 64 | Sustain pedal | — | — |
| 66 | Sostenuto | — | — |
| — | Pattern mute | 1 | 104 |

---

## MIDI Gotchas & Tips

### CC MSB/LSB pairs
Many Digitone parameters use dual CC (MSB + LSB) for higher resolution. The MSB is the primary CC, and the LSB is MSB+32. For simple control, sending just the MSB works at 7-bit resolution (128 steps). For full resolution, send both MSB then LSB.

Example: Filter Frequency = CC 23 (MSB) + CC 55 (LSB)

### NRPN message format
Same as Digitakt: 4 CC messages in sequence:
1. CC 99 = NRPN MSB (parameter number high byte)
2. CC 98 = NRPN LSB (parameter number low byte)
3. CC 6 = Data MSB (value high byte)
4. CC 38 = Data LSB (value low byte, optional for 7-bit)

### Ratio offsets are NRPN-only
The ratio offset parameters (fine-tuning of operators) have no CC mapping. They have ~2000 discrete values requiring 14-bit NRPN resolution.

### FX channel is separate
Global effects (Chorus, Delay, Reverb) are controlled on the FX channel, not on individual track channels. Track-level sends (Chorus send, Delay send, Reverb send) are on the track's own channel.

### Known FX CC bug
Community reports that some global FX parameters don't respond to CC via internal MIDI tracks, though they work from external sources. Delay Time (CC15) works; other delay params may not respond consistently.

### MIDI stress
Sending too many NRPN messages rapidly can cause envelope timing issues. Be careful with CC 83 and CC 86 (operator A/B delay) - stray CC messages can accidentally shift operator envelopes.

### Program change
- Enable in `MIDI CONFIG > SYNC > PROG CH RECEIVE`
- PC#1 = Pattern A1, PC#2 = Pattern A2, etc.
- Send PC slightly before the pattern boundary (not at the start of the bar)

### Auto Channel
Default channel 10. Sends to whichever track is currently active. Useful for "play the current track" workflows.

---

## Best Parameters to Automate via MIDI

### High-impact FM parameters

| Parameter | CC | Why |
|-----------|-----|-----|
| Feedback | 19 | Adds harmonics/grit. Small changes = big timbral shifts |
| Mix (X/Y) | 20 | Crossfades between two sides of algorithm. Morphs sounds |
| A level | 78 | Controls modulator depth = modulation index |
| B level | 82 | Same for B operator pair |
| Ratio B | 16+48 | Changing ratio = dramatic timbral shift |
| Harmonics | 17 | Shifts harmonic content |
| Detune | 18 | Subtle beating/chorus effects |

### Classic automation moves

| Technique | Parameters | Effect |
|-----------|------------|--------|
| Filter sweep | CC 23 (frequency) | Classic synth sweep |
| FM morph | CC 20 (mix) | Crossfade between X/Y outputs |
| Growl/bite | CC 19 (feedback) | Add harmonic distortion |
| Modulation index sweep | CC 78 or 82 (A/B level) | Brighten/darken FM timbre |
| Evolving pad | LFO → filter cutoff + slow ratio sweep | Constantly shifting texture |
| Percussive pluck | Short A env decay (CC 76) + high A level | Sharp FM transient |

### LFO tips for the Digitone

- LFO2 can modulate LFO1's speed for complex modulation
- Random S&H on modulator levels adds "humanity" to sequences
- Offset LFO start phase (SPH) across tracks to avoid unison pumping
- Triangle LFO on Ratio A/B creates retro pitch warble without affecting carrier pitch

---

## What Can Be Shared with Digitakt MCP

### Fully reusable (~1,500 lines)
- `send_note()`, `send_cc()`, `send_nrpn()`, `send_sysex()` - identical MIDI primitives
- Transport tools (start, stop, continue, song position)
- MIDI clock + pattern playback framework
- Parameter sweep/envelope automation engine
- Pattern/preset JSON storage and management
- MIDI file export/import
- MIDI recording/monitoring
- Connection management (just change port name string)

### Must be new for Digitone
- `nrpn_constants.py` → completely different CC/NRPN numbers
- `parameter_map.py` → different parameter names and categories
- Track triggering → chromatic notes per track, not notes 0-7
- 2 LFOs per track instead of 1
- Chorus effect (Digitakt has none)
- FM-specific tools (algorithm selection, operator control, ratio presets)
- No sample/source parameters

### Suggested new Digitone-specific tools

| Tool | Purpose |
|------|---------|
| `set_algorithm` | Set FM algorithm (1-8) with description of routing |
| `set_operator_levels` | Set A/B levels (modulation index) |
| `set_ratios` | Set C/A/B ratios with musical descriptions |
| `set_operator_envelope` | Configure A or B operator envelope (attack, decay, end, level) |
| `play_chord` | Send multi-note chord (Digitone is polyphonic!) |
| `set_chorus` | Configure chorus effect params |
| `fm_sound_preset` | Apply named FM sound templates (e.g., "electric_piano", "brass", "bell") |

---

## Repo Structure Proposal

```
digitone-midi-mcp/              # Separate repo
├── server_fastmcp.py           # MCP server (adapted from Digitakt)
├── parameter_map.py            # Digitone CC/NRPN definitions
├── nrpn_constants.py           # Digitone NRPN constants
├── fm_presets.py               # FM sound recipe library
├── digitone_midi.py            # Entry point
├── tests/
│   ├── test_fastmcp_migration.py  # Unit tests (mocked MIDI)
│   └── test_midi.py               # Hardware tests
└── pyproject.toml
```

Data: `~/.mcp-config/digitone/patterns/`, `presets/`, `recordings/`

MIDI port name: `"Elektron Digitone"`

---

## Jamie's Hardware Setup Context

From CLAUDE.md, the Digitone receives from Digitakt MIDI tracks:
- Digitone Track 1 (chords): receives on channels 9, 10
- Digitone Track 2 (bass): receives on channels 11, 12
- Digitone Track 3 (lead): receives on channels 13, 14
- Digitone Track 4: receives on channels 15, 16

For direct USB control from computer, the Digitone would use its own channels (1-4 for synth tracks, configurable).

---

## References

- [Digitone User Manual (PDF)](https://www.elektron.se/wp-content/uploads/2024/09/Digitone_User_Manual_ENG_OS1.41_231108.pdf)
- [Digitone MIDI CC/NRPN Reference](https://midi.guide/d/elektron/digitone/)
- [Digitone FM Synthesis Guide (community)](https://docs.google.com/document/u/0/d/1dLrLAFyj1qOBhgkgtjH0oDM67nwY9DkMXg1a5tIjvx4/mobilebasic)
- [FM Synthesis with Digitone - Perfect Circuit](https://www.perfectcircuit.com/signal/fm-synthesis-elektron-digitone)
- [Elektronauts: Algorithms and Their Effects](https://www.elektronauts.com/t/algorithms-and-their-effects/105498)
- [Elektronauts: LFO Tips](https://www.elektronauts.com/t/your-best-lfo-tips-on-the-digitone/164098)
- [Elektronauts: MIDI Control](https://www.elektronauts.com/t/digitone-midi-control/109755)
