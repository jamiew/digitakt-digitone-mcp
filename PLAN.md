# Digitakt MIDI MCP Server

## Current Focus

**Digitakt 1 only** - get this working well before expanding to other devices.

This is a working MCP server with 44 tools for controlling an Elektron Digitakt via MIDI. The codebase is intentionally simple: one main server file (`server_fastmcp.py`) with all tools, plus parameter/NRPN constants.

---

## Current Architecture

```
digitakt-midi-mcp/
├── server_fastmcp.py     # FastMCP server, 44 tools (~73KB)
├── parameter_map.py      # Digitakt CC/param definitions
├── nrpn_constants.py     # Digitakt NRPN definitions
├── digitakt_midi.py      # Entry point
├── tests/                # pytest tests
└── pyproject.toml
```

### Current Tools (44 total)

| Category | Tools | Purpose |
|----------|-------|---------|
| Core MIDI | 7 | Notes, CCs, NRPN, SysEx, sequences |
| Transport | 4 | Start, stop, continue, song position |
| Trig/Step | 4 | Step note/velocity/length, reset |
| Parameters | 2 | List and set named parameters |
| Playback + Clock | 6 | Pattern playback with MIDI clock |
| Automation | 3 | Sweeps, envelopes, automation |
| Pattern Storage | 8 | Save/load patterns to JSON |
| Automation Presets | 3 | Save/load automation presets |
| MIDI Export | 3 | Export to .mid files |
| Recording | 4 | Record MIDI input |

---

## Token Usage Analysis

Understanding token costs is critical for efficient MCP design. Every tool adds to the system prompt sent with each request.

### Measuring Tool Token Overhead

Each tool contributes to context in two ways:
1. **Schema tokens**: Tool name, description, parameter schema (JSON)
2. **Discovery tokens**: Listed in tool manifest

**Rough estimates per tool** (using cl100k_base tokenizer):
- Simple tool (1-2 params, short desc): ~50-80 tokens
- Medium tool (3-5 params, full desc): ~100-150 tokens
- Complex tool (many params, long desc): ~200-300 tokens

### Current digitakt-midi-mcp Token Cost

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
| **Total** | **44** | **~4,700 tokens** |

This is sent with every request. For a typical conversation with 10 requests, that's ~47K tokens just for tool definitions.

---

## Multi-Device Architecture Options

When we're ready to support multiple Elektron devices, here are the options:

### Option A: Single Unified MCP (Not Recommended)

```
elektron-mcp (100+ tools)
├── Shared tools (39)
├── Digitakt 1/2 tools (+11)
├── Digitone 1/2 tools (+20)
├── Syntakt tools (+15)
└── Tonwerk tools (+20)
```

**Token cost**: ~12,000-15,000 tokens per request

Problems:
- Massive context overhead
- Irrelevant tools for single-device users
- LLM confusion from too many similar tools
- Slow tool discovery

### Option B: Separate MCPs Per Device (Recommended)

```
digitakt-mcp     (50 tools)  → ~5,500 tokens
digitone-mcp     (59 tools)  → ~6,500 tokens
syntakt-mcp      (56 tools)  → ~6,200 tokens
tonwerk-mcp      (64 tools)  → ~7,000 tokens
```

User configures only the MCP they need:

```json
{
  "mcpServers": {
    "digitakt": {
      "command": "uv",
      "args": ["run", "digitakt-mcp"]
    }
  }
}
```

**Benefits**:
- Minimal context per device
- User only loads what they need
- Each MCP is self-contained
- Simpler mental model

**Drawbacks**:
- Code duplication for shared tools
- Multiple repos/packages to maintain

### Option C: Core + Device MCPs (Hybrid)

```
elektron-core-mcp (39 tools)  → ~4,200 tokens
  └── Shared: transport, notes, patterns, recording

digitakt-ext-mcp  (11 tools)  → ~1,200 tokens
  └── DT-specific: sample params, LFO, FX sends

digitone-ext-mcp  (20 tools)  → ~2,200 tokens
  └── DN-specific: FM operators, algorithms
```

User configures both:
```json
{
  "mcpServers": {
    "elektron-core": { "command": "uv", "args": ["run", "elektron-core-mcp"] },
    "digitakt": { "command": "uv", "args": ["run", "digitakt-ext-mcp"] }
  }
}
```

**Total for Digitakt**: ~5,400 tokens (similar to Option B)

**Benefits**:
- No code duplication
- Shared tools maintained once
- Device-specific extensions are small

**Drawbacks**:
- More complex setup (2 MCPs needed)
- Coordination between MCPs
- User must configure multiple servers

### Option D: Dynamic Tool Loading (Advanced)

Single MCP that loads tools based on detected device:

```python
def register_tools(mcp: FastMCP):
    # Always register core
    register_core_tools(mcp)       # 39 tools

    # Detect and register device-specific
    device = detect_connected_device()
    if device == "digitakt":
        register_digitakt_tools(mcp)  # +11 tools
    elif device == "digitone":
        register_digitone_tools(mcp)  # +20 tools
```

**Token cost**: ~5,000-7,000 depending on device

**Benefits**:
- Single MCP to configure
- Automatic device detection
- Minimal tools loaded

**Drawbacks**:
- Complex implementation
- Tools change based on hardware
- Harder to test

---

## Token Efficiency Strategies

### 1. Tool Consolidation

Instead of many granular tools, use fewer flexible tools:

**Before** (12 tools):
```
set_filter_cutoff, set_filter_resonance, set_filter_type,
set_amp_volume, set_amp_pan, set_amp_attack, set_amp_decay,
set_lfo_speed, set_lfo_depth, set_lfo_destination, ...
```

**After** (2 tools):
```
set_parameter(name, value)   # Generic param setter
list_parameters(category?)   # List available params
```

**Savings**: ~800 tokens

### 2. Description Compression

Keep descriptions minimal:

**Before** (~150 tokens):
```python
@mcp.tool
def send_note(
    note: int,
    velocity: int = 100,
    duration: float = 0.5,
    channel: int = 1
) -> str:
    """
    Send a MIDI note on/off pair to the Digitakt.

    This sends a note_on message followed by a note_off after the
    specified duration. The note value should be 0-127 where 60 is
    middle C. Velocity controls how hard the note is played.

    Args:
        note: MIDI note number (0-127, 60=C4)
        velocity: Note velocity (0-127, default 100)
        duration: Note length in seconds (default 0.5)
        channel: MIDI channel (1-16, default 1)

    Returns:
        Confirmation message
    """
```

**After** (~60 tokens):
```python
@mcp.tool
def send_note(
    note: int,
    velocity: int = 100,
    duration: float = 0.5,
    channel: int = 1
) -> str:
    """Send MIDI note. note=0-127 (60=C4), velocity=0-127, duration in seconds."""
```

**Savings across 44 tools**: ~2,000-3,000 tokens

### 3. Tool Grouping with Resources

Move reference info to MCP resources instead of tool descriptions:

```python
@mcp.resource("midi://parameters")
def get_parameter_list():
    """Returns all available parameters with descriptions"""
    return PARAMETER_DOCS

@mcp.tool
def set_parameter(name: str, value: int) -> str:
    """Set param by name. See midi://parameters for list."""
```

LLM can fetch the resource once, reducing per-request overhead.

---

## Recommended Architecture

For now: **Keep it simple with Option B**.

```
This repo (digitakt-midi-mcp):
├── 44 tools for Digitakt 1
├── Self-contained, no dependencies on other MCPs
├── ~4,700 tokens per request
└── Works great for single-device use

Future (when needed):
├── Create digitone-mcp as separate repo
├── Copy shared code (it's not that much)
├── Each MCP is ~5-7K tokens
└── User enables only what they need
```

### Why Not Abstract Now?

1. **YAGNI** - We don't need multi-device yet
2. **Shared code is small** - ~1,500 lines of truly shared logic
3. **Premature abstraction is costly** - Harder to iterate
4. **Copy is fine** - When we add Digitone, copy what works
5. **Refactor later** - Extract shared package when patterns emerge

---

## Elektron Device Comparison (for future reference)

| Device | Audio Tracks | MIDI Tracks | LFOs | Steps | Unique Features |
|--------|--------------|-------------|------|-------|-----------------|
| Digitakt 1 | 8 | 8 | 1 | 64 | Sampling, sample locks |
| Digitakt 2 | 16 | 16 | 3 | 128 | Wavetable, more voices |
| Digitone 1 | 4 | 4 | 2 | 64 | FM synthesis |
| Digitone 2 | 16 | 16 | 2 | 128 | Wavetone, Swarmer engines |
| Syntakt | 12 | - | 2 | 64 | Analog + digital machines |
| Tonwerk | 16 | - | 2 | 128 | Multisampling, subtracks |

### Shared MIDI (works on all devices)

| Feature | CC/Method |
|---------|-----------|
| Track Mute | CC 94 |
| Track Level | CC 95 |
| Transport | Start/Stop/Continue |
| Clock | 24 PPQ |
| NRPN | MSB(99) + LSB(98) + Data(6,38) |

---

## Next Steps

1. **Optimize current tools** - Compress descriptions, consolidate where sensible
2. **Measure actual tokens** - Add token counting to tests
3. **Improve reliability** - Better error handling, connection management
4. **Document usage** - Examples, patterns, common workflows
5. **Future: Digitone** - When needed, create separate MCP

---

## Token Budget Guidelines

| Scenario | Max Tools | Max Tokens | Notes |
|----------|-----------|------------|-------|
| Single device | 50-60 | ~6,000 | Comfortable |
| Two devices | 80-100 | ~10,000 | Acceptable |
| All devices | 150+ | ~15,000+ | Too heavy |

**Rule of thumb**: Keep each MCP under 6,000 tokens for responsive performance.

---

## Resources

- [Digitakt Manual](https://www.elektron.se/wp-content/uploads/2024/09/Digitakt_User_Manual_ENG_OS1.51_231108.pdf)
- [Elektron MIDI Guide](https://midi.guide/d/elektron/)
- [MCP Specification](https://modelcontextprotocol.io/)
