#!/usr/bin/env python3
"""
Digitakt (original) MIDI CC and NRPN Constants

Source: Digitakt User Manual, Appendix A
Reference: https://midi.guide/d/elektron/digitakt/

NRPNs provide access to more parameters than standard MIDI CCs.
Each NRPN requires sending 4 CC messages to set a value.

Structure:
  MSB (CC 99) = Category
  LSB (CC 98) = Parameter
  Data Entry MSB (CC 6) = Value (0-127)
  Data Entry LSB (CC 38) = Fine value (usually 0)

NOTE: Digitakt 1 has 8 audio tracks (not 16 like Digitakt II)
      Digitakt 1 has only 1 LFO (not 3 like Digitakt II)
      Digitakt 1 has no Chorus effect
"""

# ============================================================================
# MIDI CC CONSTANTS
# ============================================================================


class TrackCC:
    """Track-level CC parameters"""

    SOLO = 93
    MUTE = 94  # Global mute
    LEVEL = 95
    PATTERN_MUTE = 110


class SourceCC:
    """Source/sample CC parameters"""

    TUNE = 16
    PLAY_MODE = 17
    BIT_REDUCTION = 18
    SAMPLE_SLOT = 19
    SAMPLE_START = 20
    SAMPLE_LENGTH = 21
    SAMPLE_LOOP = 22
    SAMPLE_LEVEL = 23


class FilterCC:
    """Filter envelope CC parameters"""

    ATTACK = 70
    DECAY = 71
    SUSTAIN = 72
    RELEASE = 73
    FREQUENCY = 74
    RESONANCE = 75
    TYPE = 76
    ENV_DEPTH = 77


class AmpCC:
    """AMP envelope CC parameters - NOTE: Different from Digitakt II!"""

    ATTACK = 78  # CC 78 (not 79 like DT2)
    HOLD = 79  # CC 79 (not 80 like DT2)
    DECAY = 80  # CC 80 (not 81 like DT2)
    OVERDRIVE = 81  # CC 81 - Overdrive is in AMP section on DT1
    DELAY_SEND = 82  # CC 82 - Delay send is in AMP section on DT1
    REVERB_SEND = 83  # CC 83 - Reverb send is in AMP section on DT1
    PAN = 10  # CC 10 (not 90 like DT2)
    VOLUME = 7  # CC 7 (not 89 like DT2)


class FXCC:
    """Effects CC parameters - NOTE: No Chorus on Digitakt 1!"""

    # FX sends are in AmpCC on Digitakt 1
    DELAY_SEND = 82  # Same as AmpCC.DELAY_SEND
    REVERB_SEND = 83  # Same as AmpCC.REVERB_SEND
    # No Chorus on Digitakt 1!


class TrigCC:
    """Trig CC parameters"""

    NOTE = 3
    VELOCITY = 4
    LENGTH = 5
    FILTER_TRIG = 13
    LFO_TRIG = 14


class LfoCC:
    """LFO CC parameters - Only 1 LFO on Digitakt 1"""

    SPEED = 102
    MULTIPLIER = 103
    FADE = 104
    DESTINATION = 105
    WAVEFORM = 106
    START_PHASE = 107
    TRIG_MODE = 108
    DEPTH = 109  # Also uses CC 118 for LSB


class DelayCC:
    """Delay FX CC parameters"""

    TIME = 85
    PINGPONG = 86
    STEREO_WIDTH = 87
    FEEDBACK = 88
    HPF = 89
    LPF = 90
    REVERB_SEND = 91
    MIX = 92


class ReverbCC:
    """Reverb FX CC parameters"""

    PREDELAY = 24
    DECAY = 25
    SHELVING_FREQ = 2
    SHELVING_GAIN = 27
    HPF = 28
    LPF = 29
    MIX = 31


# ============================================================================
# NRPN CONSTANTS
# ============================================================================


# NRPN MSB Categories
class NRPN_MSB:
    TRACK_TRIG_SOURCE_FILTER_AMP = 1
    FX = 2
    TRIG_NOTE_VEL_LEN = 3


# Track Parameters (MSB 1)
class TrackParams:
    MSB = 1
    LEVEL = 100
    GLOBAL_MUTE = 101
    SOLO = 102
    PATTERN_MUTE = 104


# Trig Parameters (MSB 3 for note/velocity/length)
class TrigParams:
    MSB = 3
    NOTE = 0
    VELOCITY = 1
    LENGTH = 2


# Source Parameters (MSB 1, LSB 0-7)
class SourceParams:
    MSB = 1
    TUNE = 0
    PLAY_MODE = 1
    BIT_REDUCTION = 2
    SAMPLE_SLOT = 3
    SAMPLE_START = 4
    SAMPLE_LENGTH = 5
    SAMPLE_LOOP = 6
    SAMPLE_LEVEL = 7


# Filter Parameters (MSB 1, LSB 16-23)
class FilterParams:
    MSB = 1
    ATTACK = 16
    DECAY = 17
    SUSTAIN = 18
    RELEASE = 19
    FREQUENCY = 20
    RESONANCE = 21
    TYPE = 22
    ENVELOPE_DEPTH = 23


# Amp Parameters (MSB 1, LSB 24-31)
# NOTE: Different layout from Digitakt II
class AmpParams:
    MSB = 1
    ATTACK = 24
    HOLD = 25
    DECAY = 26
    OVERDRIVE = 27
    DELAY_SEND = 28
    REVERB_SEND = 29
    PAN = 30
    VOLUME = 31


# LFO Parameters (MSB 1, LSB 32-39)
# NOTE: Digitakt 1 has only ONE LFO (not 3 like Digitakt II)
class LFOParams:
    MSB = 1
    SPEED = 32
    MULTIPLIER = 33
    FADE = 34
    DESTINATION = 35
    WAVEFORM = 36
    START_PHASE = 37
    TRIG_MODE = 38
    DEPTH = 39


# Alias for compatibility - Digitakt 1 only has one LFO
LFO1Params = LFOParams


# Delay FX Parameters (MSB 2, LSB 0-7)
class DelayParams:
    MSB = 2
    TIME = 0
    PINGPONG = 1
    STEREO_WIDTH = 2
    FEEDBACK = 3
    HPF = 4
    LPF = 5
    REVERB_SEND = 6
    MIX = 7


# Reverb FX Parameters (MSB 2, LSB 8-15)
class ReverbParams:
    MSB = 2
    PREDELAY = 8
    DECAY = 9
    SHELVING_FREQ = 10
    SHELVING_GAIN = 11
    HPF = 12
    LPF = 13
    MIX = 15


# NOTE: No Chorus on Digitakt 1!
# Keeping this empty class for code compatibility
class ChorusParams:
    MSB = 2
    # No chorus on Digitakt 1


# Helper dictionary for parameter names
NRPN_PARAMS = {
    (1, 100): "Track Level",
    (1, 101): "Global Mute",
    (1, 102): "Solo",
    (1, 104): "Pattern Mute",
    (3, 0): "Trig Note",
    (3, 1): "Trig Velocity",
    (3, 2): "Trig Length",
    (1, 0): "Source Tune",
    (1, 1): "Source Play Mode",
    (1, 2): "Source Bit Reduction",
    (1, 3): "Sample Slot",
    (1, 4): "Sample Start",
    (1, 5): "Sample Length",
    (1, 6): "Sample Loop",
    (1, 7): "Sample Level",
    (1, 16): "Filter Attack",
    (1, 17): "Filter Decay",
    (1, 18): "Filter Sustain",
    (1, 19): "Filter Release",
    (1, 20): "Filter Frequency",
    (1, 21): "Filter Resonance",
    (1, 22): "Filter Type",
    (1, 23): "Filter Envelope Depth",
    (1, 24): "Amp Attack",
    (1, 25): "Amp Hold",
    (1, 26): "Amp Decay",
    (1, 27): "Amp Overdrive",
    (1, 28): "Delay Send",
    (1, 29): "Reverb Send",
    (1, 30): "Pan",
    (1, 31): "Volume",
    (1, 32): "LFO Speed",
    (1, 33): "LFO Multiplier",
    (1, 34): "LFO Fade",
    (1, 35): "LFO Destination",
    (1, 36): "LFO Waveform",
    (1, 37): "LFO Start Phase",
    (1, 38): "LFO Trig Mode",
    (1, 39): "LFO Depth",
    (2, 0): "Delay Time",
    (2, 1): "Delay Pingpong",
    (2, 2): "Delay Stereo Width",
    (2, 3): "Delay Feedback",
    (2, 4): "Delay HPF",
    (2, 5): "Delay LPF",
    (2, 6): "Delay Reverb Send",
    (2, 7): "Delay Mix",
    (2, 8): "Reverb Predelay",
    (2, 9): "Reverb Decay",
    (2, 10): "Reverb Shelving Freq",
    (2, 11): "Reverb Shelving Gain",
    (2, 12): "Reverb HPF",
    (2, 13): "Reverb LPF",
    (2, 15): "Reverb Mix",
}


def get_param_name(msb: int, lsb: int) -> str:
    """Get the human-readable name for an NRPN parameter"""
    return NRPN_PARAMS.get((msb, lsb), f"Unknown NRPN {msb}:{lsb}")
