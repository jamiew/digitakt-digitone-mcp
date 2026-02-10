# Digitakt MIDI MCP Server

An MCP (Model Context Protocol) server for controlling the Elektron Digitakt (original) via MIDI.

> **Note:** This is for the **original Digitakt**, NOT Digitakt II. Key differences:
> - 8 audio tracks (not 16)
> - 8 MIDI tracks (separate, unlike Digitakt II where any track can be MIDI)
> - Only 1 LFO (not 3)
> - No Chorus effect
> - Different AMP CC numbers (Volume=CC 7, Pan=CC 10)

## Project Structure

```
digitakt-midi-mcp/
├── pyproject.toml         # Project config (uv)
├── server_fastmcp.py      # FastMCP server (44 tools)
├── digitakt_midi.py       # Entry point
├── nrpn_constants.py      # MIDI NRPN mappings
├── parameter_map.py       # Named parameter → CC/NRPN mapping
├── tests/                 # Unit + hardware tests
└── PLAN.md                # TODO list and architecture
```

## Features

- **MIDI Notes**: Trigger tracks (1-8), play melodies, sequences
- **Parameter Control**: Named parameters via `set_parameter` (filter, amp, LFO, FX)
- **Transport**: Start/stop/continue, song position, MIDI clock sync
- **Pattern Playback**: Multi-track triggers, melodies, loops with clock
- **Automation**: Parameter sweeps, ADSR envelopes, real-time modulation
- **Pattern Storage**: Save/load patterns and automation presets to JSON
- **MIDI Export**: Export patterns and melodies to .mid files
- **MIDI Recording**: Monitor and record incoming MIDI to .mid files

## Installation

1. **Install uv** (if you don't have it):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. **Clone and sync dependencies:**
```bash
git clone <repo-url>
cd digitakt-midi-mcp
uv sync
```

3. **Connect your Digitakt via USB**:
   - Connect the Digitakt to your computer via USB
   - The Digitakt should appear as a MIDI device named "Elektron Digitakt"
   - On macOS, you can verify in Audio MIDI Setup that the device is visible
   - If using Overbridge, make sure Overbridge Engine is running

4. **Configure Digitakt MIDI Settings for Multi-Track Triggering:**

The MCP server sends track triggers on per-track MIDI channels (Track 1 on Channel 1, Track 2 on Channel 2, etc.). To enable simultaneous triggering of multiple tracks, you must configure your Digitakt:

**Settings → MIDI Config → Channels:**
- **Option A: Per-Track Channels (Recommended for MCP)**
  - Set each track to its corresponding MIDI channel:
    - Track 1: Channel 1
    - Track 2: Channel 2
    - ...
    - Track 8: Channel 8
  - This allows the MCP server to trigger multiple tracks simultaneously

- **Option B: Auto Channel (Simple but Limited)**
  - Set all tracks to "Auto Channel" (default)
  - Only the currently selected track will respond to triggers
  - You cannot trigger multiple tracks simultaneously from the MCP server

**To set per-track channels on Digitakt:**
1. Press **[FUNC] + [SETTINGS]**
2. Navigate to **MIDI** → **CONFIG** → **CHANNELS**
3. For each track (TRK 1-8), set MIDI IN channel to match track number
4. Save settings

**Enable MIDI transport control:**
1. Press **[FUNC] + [SETTINGS]**
2. Navigate to **MIDI** → **SYNC**
3. Set **CLOCK RECEIVE** to **ON**
4. Set **TRANSPORT RECEIVE** to **ON**
5. Save settings

## Usage

### Running the Server Manually

```bash
uv run digitakt-midi
```

### Configuring with Claude Desktop

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "digitakt-midi": {
      "command": "uv",
      "args": ["--directory", "/path/to/digitakt-midi-mcp", "run", "digitakt-midi"]
    }
  }
}
```

Replace `/path/to/digitakt-midi-mcp` with the actual path to this directory.

Then restart Claude Desktop.

## Available Tools

### send_note
Send a MIDI note to trigger drums on the Digitakt.

**Parameters:**
- `note` (required): MIDI note number (0-127). Notes 0-7 trigger tracks 1-8. Notes 12-84 play active track chromatically.
- `velocity` (optional): Note velocity (1-127), default 100
- `duration` (optional): How long to hold the note in seconds, default 0.1
- `channel` (optional): MIDI channel (1-16), default 1

**Examples:**
```
Play note 0 to trigger track 1 (kick)
Play note 60 on the active track
```

### trigger_track
Trigger a one-shot sample on a specific Digitakt track (convenience wrapper).

**Parameters:**
- `track` (required): Track number (1-8)
- `velocity` (optional): Note velocity (1-127), default 100
- `duration` (optional): How long to hold the note in seconds, default 0.1
- `channel` (optional): MIDI channel (1-16), default 1

**Examples:**
```
Trigger track 1 (kick)
Trigger track 8 with velocity 127
```

### send_cc
Send a Control Change message to adjust Digitakt parameters.

**Parameters:**
- `cc_number` (required): CC number (0-127)
- `value` (required): CC value (0-127)
- `channel` (optional): MIDI channel (1-16), default 1

**Common CC Numbers for Digitakt (original):**

**Track:**
- 93: Solo
- 94: Mute
- 95: Track Level
- 110: Pattern Mute

**Source:**
- 16: Tune
- 17: Play Mode
- 18: Bit Reduction
- 19-23: Sample Slot, Start, Length, Loop, Level

**Filter Envelope:**
- 70: Attack Time
- 71: Decay Time
- 72: Sustain Level
- 73: Release Time
- 74: Filter Frequency
- 75: Resonance
- 76: Filter Type
- 77: Envelope Depth

**AMP Envelope (different from Digitakt II!):**
- 78: Attack Time
- 79: Hold Time
- 80: Decay Time
- 81: Overdrive
- 82: Delay Send
- 83: Reverb Send
- 10: Pan
- 7: Volume

**LFO (only 1 LFO, not 3 like Digitakt II):**
- 102-109: LFO Speed, Multiplier, Fade, Destination, Waveform, Start Phase, Trig Mode, Depth

**Delay FX:**
- 85-92: Time, Pingpong, Stereo Width, Feedback, HPF, LPF, Reverb Send, Mix

**Reverb FX:**
- 24: Predelay
- 25: Decay
- 2: Shelving Freq
- 27-29: Shelving Gain, HPF, LPF
- 31: Mix

**Note:** The original Digitakt does NOT have Chorus (that's Digitakt II only).

### send_program_change
Switch to a different pattern on the Digitakt.

**Parameters:**
- `program` (required): Pattern number (0-127)
- `channel` (optional): MIDI channel (1-16), default 1

### send_nrpn
Send an NRPN (Non-Registered Parameter Number) message for advanced parameter control.

**Parameters:**
- `msb` (required): NRPN MSB (1=Track/Trig/Source/Filter/Amp/LFO, 2=FX, 3=Trig Note/Velocity/Length)
- `lsb` (required): NRPN LSB (parameter number)
- `value` (required): Parameter value (0-127)
- `channel` (optional): MIDI channel (1-16), default 1

**Common NRPNs:**
- MSB=3, LSB=0: Trig Note
- MSB=3, LSB=1: Trig Velocity
- MSB=3, LSB=2: Trig Length
- MSB=1, LSB=20: Filter Frequency
- MSB=1, LSB=21: Filter Resonance

### Transport Control

#### send_midi_start
Send MIDI Start message to start the Digitakt's sequencer from the beginning.

#### send_midi_stop
Send MIDI Stop message to stop the Digitakt's sequencer.

#### send_midi_continue
Send MIDI Continue message to resume the Digitakt's sequencer from its current position.

#### send_song_position
Send MIDI Song Position Pointer to jump to a specific position in the sequence.

**Parameters:**
- `position` (required): Song position in MIDI beats (16th notes). 0 = start, 16 = 1 bar in 4/4 time.

### play_with_clock
Start the Digitakt sequencer and send MIDI clock for a specified duration.

**Parameters:**
- `bars` (optional): Number of bars to play in 4/4 time. Default is 4 bars.
- `bpm` (optional): Tempo in beats per minute. Default is 120 BPM.
- `send_stop` (optional): Send MIDI Stop after duration. Default is true.

### play_pattern_with_tracks
Start the Digitakt pattern and trigger specific tracks at specific times.

**Parameters:**
- `bars` (optional): Number of bars to play. Default is 4.
- `bpm` (optional): Tempo in BPM. Default is 120.
- `triggers` (required): Array of `[beat, track, velocity]` where beat is 0-based quarter note, track is 1-8, velocity is 1-127.
- `send_stop` (optional): Send MIDI Stop after duration. Default is true.

### play_pattern_with_melody
Start the Digitakt pattern and play a melodic sequence on the active track.

**Parameters:**
- `bars` (optional): Number of bars to play. Default is 4.
- `bpm` (optional): Tempo in BPM. Default is 120.
- `notes` (required): Array of `[beat, note, velocity, duration]` where beat is 0-based quarter note, note is MIDI note 12-127, velocity is 1-127, duration is in seconds.
- `channel` (optional): MIDI channel (1-16). Default is 1.
- `send_stop` (optional): Send MIDI Stop after duration. Default is true.

## Parameter Automation Framework

The Digitakt MIDI MCP server includes a powerful parameter automation framework for creating dynamic, evolving sounds.

**Important:** Parameter automation is sent in real-time via MIDI and is NOT saved to Digitakt patterns.

### Preset Storage Location

All automation presets are stored in: `~/.mcp-config/digitakt/presets/`

### Available Parameters

Use the `list_parameters` tool to see all available parameters:
- **Filter**: cutoff, resonance, type, envelope (ADSR + depth)
- **Amp**: volume, pan, attack, hold, decay, overdrive
- **Source/Sample**: tune, bit reduction, sample start/length/loop/level
- **LFO**: speed, multiplier, fade, destination, waveform, start phase, trig mode, depth
- **FX Sends**: delay, reverb (no chorus on original Digitakt!)
- **Delay/Reverb FX**: detailed parameters for each effect
- **Track**: level, mute, solo
- **Trig**: note, velocity, length

### set_parameter

Set any parameter to a specific value instantly.

**Parameters:**
- `parameter` (required): Parameter name (e.g., 'filter_cutoff', 'lfo_depth', 'amp_volume')
- `value` (required): Parameter value (0-127)
- `channel` (optional): MIDI channel (1-16), default 1

**Channel Routing:**
On the Digitakt, each track (1-8) has its own MIDI channel (1-8). To control parameters on a specific track:
- Track 1 parameters → channel 1
- Track 8 parameters → channel 8

### send_parameter_sweep

Smoothly sweep any parameter from one value to another over a specified duration.

**Parameters:**
- `parameter` (required): Parameter name
- `start_value` (required): Starting value (0-127)
- `end_value` (required): Ending value (0-127)
- `duration_sec` (required): Duration in seconds
- `curve` (optional): 'linear', 'exponential', or 'logarithmic', default 'linear'
- `steps` (optional): Number of messages to send, default 50
- `channel` (optional): MIDI channel (1-16), default 1

### send_parameter_envelope

Apply an ADSR-style envelope to any parameter.

**Parameters:**
- `parameter` (required): Parameter name
- `attack_sec` (required): Attack time (time to reach peak 127)
- `decay_sec` (required): Decay time (time to drop to sustain level)
- `sustain_level` (required): Sustain value (0-127)
- `release_sec` (required): Release time (time to return to 0)
- `steps_per_stage` (optional): Messages per stage, default 20
- `channel` (optional): MIDI channel (1-16), default 1

## Digitakt MIDI Reference

### Note Numbers for Tracks

**To trigger one-shots on specific audio tracks (1-8):**
- Track 1: MIDI note **0** (C-2)
- Track 2: MIDI note **1** (C#-2)
- Track 3: MIDI note **2** (D-2)
- Track 4: MIDI note **3** (D#-2)
- Track 5: MIDI note **4** (E-2)
- Track 6: MIDI note **5** (F-2)
- Track 7: MIDI note **6** (F#-2)
- Track 8: MIDI note **7** (G-2)

**To play the currently active track chromatically:**
- MIDI notes **12 and above** (C0+) will play the active track at different pitches

**Note:** MIDI channels 1-8 can be assigned to tracks 1-8, or use AUTO CHANNEL to control the currently active track.

### NRPN Parameters

NRPNs provide access to more parameters than standard CCs. See `nrpn_constants.py` for the complete parameter list.

**NRPN Structure:**
- MSB (CC 99): Category (1, 2, or 3)
- LSB (CC 98): Specific parameter
- Data Entry MSB (CC 6): Value (0-127)
- Data Entry LSB (CC 38): Fine value (usually 0)

**Categories:**
- **MSB 1**: Track, Source, Filter, Amp, LFO parameters
- **MSB 2**: FX (Delay and Reverb) parameters
- **MSB 3**: Trig parameters (Note, Velocity, Length)

## Testing

```bash
# Unit tests (no hardware needed)
uv run pytest tests/test_fastmcp_migration.py -v

# All tests (requires connected Digitakt)
uv run pytest

# Lint and format check
uv run ruff check . && uv run ruff format --check .
```

## Troubleshooting

**MIDI device not found:**
- Make sure the Digitakt is connected via USB
- Check that the device shows up in Audio MIDI Setup (macOS)
- The device should appear as "Elektron Digitakt" (without "II")
- If using Overbridge, make sure the Overbridge Engine is running

**No sound when triggering:**
- Check that MIDI transport receive is enabled (Settings → MIDI → Sync)
- Verify the MIDI channel configuration matches your setup
- Make sure the track has a sample loaded

**Permission errors:**
- On macOS, you may need to grant microphone permissions to Terminal/iTerm
- Check System Preferences > Security & Privacy > Privacy > Microphone

## Key Differences from Digitakt II

If you're coming from Digitakt II documentation, note these important differences:

| Feature | Digitakt (original) | Digitakt II |
|---------|---------------------|-------------|
| Audio Tracks | 8 | 16 |
| MIDI Tracks | 8 (separate) | Any track |
| LFOs | 1 | 3 |
| Chorus Effect | ❌ | ✅ |
| Compressor | ❌ | ✅ |
| Volume CC | 7 | 89 |
| Pan CC | 10 | 90 |
| AMP Attack CC | 78 | 79 |
| AMP Hold CC | 79 | 80 |
| AMP Decay CC | 80 | 81 |
| Delay Send CC | 82 | 84 |
| Reverb Send CC | 83 | 85 |

## Resources

- [Digitakt User Manual (PDF)](https://www.elektron.se/wp-content/uploads/2024/09/Digitakt_User_Manual_ENG_OS1.51_231108.pdf)
- [Digitakt MIDI Implementation](https://midi.guide/d/elektron/digitakt/)
- [Elektronauts Forum](https://www.elektronauts.com/)

## License

MIT
