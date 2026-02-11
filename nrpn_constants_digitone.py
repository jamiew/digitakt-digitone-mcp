"""
Digitone (original) MIDI CC and NRPN Constants

Source: https://midi.guide/d/elektron/digitone/
See also: DIGITONE_RESEARCH.md

NRPNs require sending 4 CC messages: CC99 (MSB), CC98 (LSB), CC6 (data), CC38 (data LSB).

Key differences from Digitakt:
  - 4 synth tracks (not 8 audio tracks)
  - 4-operator FM synthesis engine (not sample player)
  - 2 LFOs per track (not 1)
  - Has Chorus effect (Digitakt has none)
  - Different CC/NRPN numbers throughout
"""


# ============================================================================
# MIDI CC CONSTANTS
# ============================================================================


class TrackCC:
    MUTE = 94
    LEVEL = 95


class TrigCC:
    ROOT_NOTE = 3
    VELOCITY = 4
    LENGTH = 5
    FILTER_TRIG = 13
    LFO_TRIG = 14
    PORTAMENTO_TIME = 15
    PORTAMENTO_ON = 16


class Syn1CC:
    """FM Synthesis page 1 - Algorithm, Ratios, Mix"""

    ALGORITHM = 90
    RATIO_C = 91
    RATIO_A = 92
    RATIO_B_MSB = 16
    RATIO_B_LSB = 48
    HARMONICS_MSB = 17
    HARMONICS_LSB = 49
    DETUNE_MSB = 18
    DETUNE_LSB = 50
    FEEDBACK_MSB = 19
    FEEDBACK_LSB = 51
    MIX_MSB = 20
    MIX_LSB = 52


class Syn2CC:
    """FM Synthesis page 2 - Operator envelopes"""

    A_ENV_ATTACK = 75
    A_ENV_DECAY = 76
    A_ENV_END = 77
    A_LEVEL = 78
    B_ENV_ATTACK = 79
    B_ENV_DECAY = 80
    B_ENV_END = 81
    B_LEVEL = 82
    A_DELAY = 83
    A_TRIG = 84
    A_ENV_RESET = 85
    B_DELAY = 86
    B_TRIG = 87
    B_ENV_RESET = 88
    PHASE_RESET = 89


class FilterCC:
    FREQUENCY_MSB = 23
    FREQUENCY_LSB = 55
    RESONANCE_MSB = 24
    RESONANCE_LSB = 56
    TYPE = 74
    ENV_ATTACK = 70
    ENV_DECAY = 71
    ENV_SUSTAIN = 72
    ENV_RELEASE = 73
    ENV_DEPTH_MSB = 25
    ENV_DEPTH_LSB = 57
    ENV_DELAY = 43
    BASE_MSB = 26
    BASE_LSB = 58
    WIDTH_MSB = 27
    WIDTH_LSB = 59


class AmpCC:
    ATTACK = 104
    DECAY = 105
    SUSTAIN = 106
    RELEASE = 107
    DRIVE_MSB = 9
    DRIVE_LSB = 41
    PAN_MSB = 10
    PAN_LSB = 42
    VOLUME_MSB = 7
    VOLUME_LSB = 39
    CHORUS_SEND_MSB = 12
    CHORUS_SEND_LSB = 44
    DELAY_SEND_MSB = 13
    DELAY_SEND_LSB = 45
    REVERB_SEND_MSB = 14
    REVERB_SEND_LSB = 46
    ENV_RESET = 102


class Lfo1CC:
    SPEED_MSB = 28
    SPEED_LSB = 60
    MULTIPLIER = 108
    FADE = 109
    DESTINATION = 110
    WAVEFORM = 111
    START_PHASE = 112
    TRIG_MODE = 113
    DEPTH_MSB = 29
    DEPTH_LSB = 61


class Lfo2CC:
    SPEED_MSB = 30
    SPEED_LSB = 62
    MULTIPLIER = 114
    FADE = 115
    DESTINATION = 116
    WAVEFORM = 117
    START_PHASE = 118
    TRIG_MODE = 119
    DEPTH_MSB = 31
    DEPTH_LSB = 63


class ChorusCC:
    """Chorus FX parameters - sent on FX channel"""

    DEPTH_MSB = 3
    DEPTH_LSB = 35
    SPEED_MSB = 9
    SPEED_LSB = 41
    HP = 70
    WIDTH = 71
    DELAY_SEND_MSB = 12
    DELAY_SEND_LSB = 44
    REVERB_SEND_MSB = 13
    REVERB_SEND_LSB = 45
    MIX = 14


class DelayCC:
    """Delay FX parameters - sent on FX channel"""

    TIME_MSB = 15
    TIME_LSB = 47
    PINGPONG_MSB = 16
    PINGPONG_LSB = 48
    STEREO_WIDTH_MSB = 17
    STEREO_WIDTH_LSB = 49
    FEEDBACK_MSB = 18
    FEEDBACK_LSB = 50
    HPF = 72
    LPF = 73
    REVERB_SEND_MSB = 19
    REVERB_SEND_LSB = 51
    MIX = 20


class ReverbCC:
    """Reverb FX parameters - sent on FX channel"""

    PREDELAY_MSB = 21
    PREDELAY_LSB = 53
    DECAY = 74
    SHELVING_FREQ = 75
    SHELVING_GAIN_MSB = 22
    SHELVING_GAIN_LSB = 54
    HPF = 76
    LPF = 77
    MIX = 23


class MasterCC:
    """Master parameters - sent on FX channel"""

    OVERDRIVE_MSB = 29
    OVERDRIVE_LSB = 61
    PATTERN_VOLUME = 95
    INPUT_L_VOLUME_MSB = 24
    INPUT_L_VOLUME_LSB = 56
    INPUT_R_VOLUME_MSB = 25
    INPUT_R_VOLUME_LSB = 57
    PAN_L = 78
    PAN_R = 79
    CHORUS_SEND_L_MSB = 26
    CHORUS_SEND_L_LSB = 58
    CHORUS_SEND_R_MSB = 30
    CHORUS_SEND_R_LSB = 62
    DELAY_SEND_L_MSB = 27
    DELAY_SEND_L_LSB = 59
    DELAY_SEND_R_MSB = 31
    DELAY_SEND_R_LSB = 63
    REVERB_SEND_L_MSB = 28
    REVERB_SEND_L_LSB = 60
    REVERB_SEND_R_MSB = 82
    REVERB_SEND_R_LSB = 32


# ============================================================================
# NRPN CONSTANTS
# ============================================================================


class NRPN_MSB:
    TRACK_PARAMS = 1  # Track, SYN1, SYN2, Filter, Amp, LFO params
    FX = 2  # Chorus, Delay, Reverb, Master params
    TRIG = 3  # Trig note, velocity, length, etc.


class TrackParams:
    MSB = 1
    LEVEL = 100
    MUTE = 101
    PATTERN_MUTE = 104


class TrigParams:
    MSB = 3
    ROOT_NOTE = 0
    VELOCITY = 1
    LENGTH = 2
    FILTER_TRIG = 5
    LFO_TRIG = 6
    PORTAMENTO_TIME = 7
    PORTAMENTO_ON = 8


class Syn1Params:
    """FM Synthesis page 1 - NRPN addresses"""

    MSB = 1
    ALGORITHM = 72
    RATIO_C = 73
    RATIO_A = 74
    RATIO_B = 75
    HARMONICS = 76
    DETUNE = 77
    FEEDBACK = 78
    MIX = 79
    # NRPN-only (no CC), 14-bit values
    RATIO_C_OFFSET = 95
    RATIO_A_OFFSET = 96
    RATIO_B1_OFFSET = 97
    RATIO_B2_OFFSET = 98


class Syn2Params:
    """FM Synthesis page 2 - Operator envelopes NRPN addresses"""

    MSB = 1
    A_ENV_ATTACK = 80
    A_ENV_DECAY = 81
    A_ENV_END = 82
    A_LEVEL = 83
    B_ENV_ATTACK = 84
    B_ENV_DECAY = 85
    B_ENV_END = 86
    B_LEVEL = 87
    A_DELAY = 88
    A_TRIG = 89
    A_ENV_RESET = 90
    B_DELAY = 91
    B_TRIG = 92
    B_ENV_RESET = 93
    PHASE_RESET = 94


class FilterParams:
    MSB = 1
    ENV_ATTACK = 16
    ENV_DECAY = 17
    ENV_SUSTAIN = 18
    ENV_RELEASE = 19
    FREQUENCY = 20
    RESONANCE = 21
    TYPE = 22
    ENV_DEPTH = 23
    BASE = 24
    WIDTH = 25
    ENV_DELAY = 66


class AmpParams:
    MSB = 1
    ATTACK = 32
    DECAY = 33
    SUSTAIN = 34
    RELEASE = 35
    DRIVE = 36
    PAN = 37
    VOLUME = 38
    REVERB_SEND = 39
    DELAY_SEND = 40
    CHORUS_SEND = 41
    ENV_RESET = 42


class LFO1Params:
    MSB = 1
    SPEED = 48
    MULTIPLIER = 49
    FADE = 50
    DESTINATION = 51
    WAVEFORM = 52
    START_PHASE = 53
    TRIG_MODE = 54
    DEPTH = 55


class LFO2Params:
    MSB = 1
    SPEED = 57
    MULTIPLIER = 58
    FADE = 59
    DESTINATION = 60
    WAVEFORM = 61
    START_PHASE = 62
    TRIG_MODE = 63
    DEPTH = 64


class ChorusParams:
    MSB = 2
    DEPTH = 0
    SPEED = 1
    HP = 2
    WIDTH = 3
    DELAY_SEND = 4
    REVERB_SEND = 5
    MIX = 6


class DelayParams:
    MSB = 2
    TIME = 10
    PINGPONG = 11
    STEREO_WIDTH = 12
    FEEDBACK = 13
    HPF = 14
    LPF = 15
    REVERB_SEND = 16
    MIX = 17


class ReverbParams:
    MSB = 2
    PREDELAY = 20
    DECAY = 21
    SHELVING_FREQ = 22
    SHELVING_GAIN = 23
    HPF = 24
    LPF = 25
    MIX = 26


class MasterParams:
    MSB = 2
    INPUT_L_VOLUME = 30
    PAN_L = 31
    INPUT_R_VOLUME = 32
    PAN_R = 33
    CHORUS_SEND_L = 34
    DELAY_SEND_L = 35
    REVERB_SEND_L = 36
    OVERDRIVE = 37
    PATTERN_VOLUME = 38
    CHORUS_SEND_R = 102
    DELAY_SEND_R = 103
    REVERB_SEND_R = 104


# ============================================================================
# LOOKUP TABLE
# ============================================================================

NRPN_PARAMS = {
    # Track
    (1, 100): "Track Level",
    (1, 101): "Mute",
    (1, 104): "Pattern Mute",
    # Trig
    (3, 0): "Root Note",
    (3, 1): "Velocity",
    (3, 2): "Length",
    (3, 5): "Filter Trig",
    (3, 6): "LFO Trig",
    (3, 7): "Portamento Time",
    (3, 8): "Portamento On",
    # SYN1 - FM
    (1, 72): "Algorithm",
    (1, 73): "Ratio C",
    (1, 74): "Ratio A",
    (1, 75): "Ratio B",
    (1, 76): "Harmonics",
    (1, 77): "Detune",
    (1, 78): "Feedback",
    (1, 79): "Mix",
    (1, 95): "Ratio C Offset",
    (1, 96): "Ratio A Offset",
    (1, 97): "Ratio B1 Offset",
    (1, 98): "Ratio B2 Offset",
    # SYN2 - Operator Envelopes
    (1, 80): "A Env Attack",
    (1, 81): "A Env Decay",
    (1, 82): "A Env End",
    (1, 83): "A Level",
    (1, 84): "B Env Attack",
    (1, 85): "B Env Decay",
    (1, 86): "B Env End",
    (1, 87): "B Level",
    (1, 88): "A Delay",
    (1, 89): "A Trig",
    (1, 90): "A Env Reset",
    (1, 91): "B Delay",
    (1, 92): "B Trig",
    (1, 93): "B Env Reset",
    (1, 94): "Phase Reset",
    # Filter
    (1, 16): "Filter Env Attack",
    (1, 17): "Filter Env Decay",
    (1, 18): "Filter Env Sustain",
    (1, 19): "Filter Env Release",
    (1, 20): "Filter Frequency",
    (1, 21): "Filter Resonance",
    (1, 22): "Filter Type",
    (1, 23): "Filter Env Depth",
    (1, 24): "Filter Base",
    (1, 25): "Filter Width",
    (1, 66): "Filter Env Delay",
    # Amp
    (1, 32): "Amp Attack",
    (1, 33): "Amp Decay",
    (1, 34): "Amp Sustain",
    (1, 35): "Amp Release",
    (1, 36): "Amp Drive",
    (1, 37): "Amp Pan",
    (1, 38): "Amp Volume",
    (1, 39): "Reverb Send",
    (1, 40): "Delay Send",
    (1, 41): "Chorus Send",
    (1, 42): "Amp Env Reset",
    # LFO 1
    (1, 48): "LFO1 Speed",
    (1, 49): "LFO1 Multiplier",
    (1, 50): "LFO1 Fade",
    (1, 51): "LFO1 Destination",
    (1, 52): "LFO1 Waveform",
    (1, 53): "LFO1 Start Phase",
    (1, 54): "LFO1 Trig Mode",
    (1, 55): "LFO1 Depth",
    # LFO 2
    (1, 57): "LFO2 Speed",
    (1, 58): "LFO2 Multiplier",
    (1, 59): "LFO2 Fade",
    (1, 60): "LFO2 Destination",
    (1, 61): "LFO2 Waveform",
    (1, 62): "LFO2 Start Phase",
    (1, 63): "LFO2 Trig Mode",
    (1, 64): "LFO2 Depth",
    # Chorus FX
    (2, 0): "Chorus Depth",
    (2, 1): "Chorus Speed",
    (2, 2): "Chorus HP",
    (2, 3): "Chorus Width",
    (2, 4): "Chorus Delay Send",
    (2, 5): "Chorus Reverb Send",
    (2, 6): "Chorus Mix",
    # Delay FX
    (2, 10): "Delay Time",
    (2, 11): "Delay Pingpong",
    (2, 12): "Delay Stereo Width",
    (2, 13): "Delay Feedback",
    (2, 14): "Delay HPF",
    (2, 15): "Delay LPF",
    (2, 16): "Delay Reverb Send",
    (2, 17): "Delay Mix",
    # Reverb FX
    (2, 20): "Reverb Predelay",
    (2, 21): "Reverb Decay",
    (2, 22): "Reverb Shelving Freq",
    (2, 23): "Reverb Shelving Gain",
    (2, 24): "Reverb HPF",
    (2, 25): "Reverb LPF",
    (2, 26): "Reverb Mix",
    # Master
    (2, 30): "Input L Volume",
    (2, 31): "Pan L",
    (2, 32): "Input R Volume",
    (2, 33): "Pan R",
    (2, 34): "Chorus Send L",
    (2, 35): "Delay Send L",
    (2, 36): "Reverb Send L",
    (2, 37): "Master Overdrive",
    (2, 38): "Pattern Volume",
    (2, 102): "Chorus Send R",
    (2, 103): "Delay Send R",
    (2, 104): "Reverb Send R",
}


def get_param_name(msb: int, lsb: int) -> str:
    """Get the human-readable name for an NRPN parameter"""
    return NRPN_PARAMS.get((msb, lsb), f"Unknown NRPN {msb}:{lsb}")
