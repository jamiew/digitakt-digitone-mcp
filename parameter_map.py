#!/usr/bin/env python3
"""
Digitakt (original) Parameter Mapping for Automation
Maps human-readable parameter names to MIDI CC/NRPN messages

NOTE: Digitakt 1 differences from Digitakt II:
- Only 8 audio tracks (vs 16)
- Only 1 LFO (vs 3)
- No Chorus effect
- Different AMP CC numbers (Volume=7, Pan=10, Attack=78, etc.)
- Delay/Reverb sends are in AMP section
"""

from nrpn_constants import (
    TrackCC, SourceCC, FilterCC, AmpCC, FXCC,
    TrackParams, TrigParams, SourceParams, FilterParams,
    AmpParams, LFOParams, LFO1Params,
    DelayParams, ReverbParams
)

# Parameter mapping: name -> {type: "cc" or "nrpn", cc: X or msb: X, lsb: Y}
PARAMETER_MAP = {
    # FILTER PARAMETERS
    "filter_cutoff": {"type": "cc", "cc": FilterCC.FREQUENCY, "range": (0, 127)},
    "filter_frequency": {"type": "cc", "cc": FilterCC.FREQUENCY, "range": (0, 127)},  # Alias
    "filter_resonance": {"type": "cc", "cc": FilterCC.RESONANCE, "range": (0, 127)},
    "filter_type": {"type": "cc", "cc": FilterCC.TYPE, "range": (0, 127)},

    # FILTER ENVELOPE
    "filter_attack": {"type": "cc", "cc": FilterCC.ATTACK, "range": (0, 127)},
    "filter_decay": {"type": "cc", "cc": FilterCC.DECAY, "range": (0, 127)},
    "filter_sustain": {"type": "cc", "cc": FilterCC.SUSTAIN, "range": (0, 127)},
    "filter_release": {"type": "cc", "cc": FilterCC.RELEASE, "range": (0, 127)},
    "filter_env_depth": {"type": "cc", "cc": FilterCC.ENV_DEPTH, "range": (0, 127)},
    "filter_envelope_depth": {"type": "cc", "cc": FilterCC.ENV_DEPTH, "range": (0, 127)},  # Alias

    # AMP PARAMETERS - Note: Different CC numbers from Digitakt II!
    "amp_volume": {"type": "cc", "cc": AmpCC.VOLUME, "range": (0, 127)},  # CC 7
    "amp_pan": {"type": "cc", "cc": AmpCC.PAN, "range": (0, 127)},        # CC 10
    "volume": {"type": "cc", "cc": AmpCC.VOLUME, "range": (0, 127)},      # Alias
    "pan": {"type": "cc", "cc": AmpCC.PAN, "range": (0, 127)},            # Alias

    # AMP ENVELOPE - Note: Different CC numbers from Digitakt II!
    "amp_attack": {"type": "cc", "cc": AmpCC.ATTACK, "range": (0, 127)},  # CC 78
    "amp_hold": {"type": "cc", "cc": AmpCC.HOLD, "range": (0, 127)},      # CC 79
    "amp_decay": {"type": "cc", "cc": AmpCC.DECAY, "range": (0, 127)},    # CC 80
    "amp_overdrive": {"type": "cc", "cc": AmpCC.OVERDRIVE, "range": (0, 127)},  # CC 81
    "overdrive": {"type": "cc", "cc": AmpCC.OVERDRIVE, "range": (0, 127)},  # Alias

    # SOURCE/SAMPLE PARAMETERS
    "tune": {"type": "cc", "cc": SourceCC.TUNE, "range": (0, 127)},
    "pitch": {"type": "cc", "cc": SourceCC.TUNE, "range": (0, 127)},  # Alias
    "play_mode": {"type": "cc", "cc": SourceCC.PLAY_MODE, "range": (0, 127)},
    "bit_reduction": {"type": "cc", "cc": SourceCC.BIT_REDUCTION, "range": (0, 127)},
    "sample_slot": {"type": "cc", "cc": SourceCC.SAMPLE_SLOT, "range": (0, 127)},
    "sample_start": {"type": "cc", "cc": SourceCC.SAMPLE_START, "range": (0, 127)},
    "sample_length": {"type": "cc", "cc": SourceCC.SAMPLE_LENGTH, "range": (0, 127)},
    "sample_loop": {"type": "cc", "cc": SourceCC.SAMPLE_LOOP, "range": (0, 127)},
    "sample_level": {"type": "cc", "cc": SourceCC.SAMPLE_LEVEL, "range": (0, 127)},

    # LFO PARAMETERS - Digitakt 1 has only ONE LFO
    "lfo_speed": {"type": "nrpn", "msb": LFOParams.MSB, "lsb": LFOParams.SPEED, "range": (0, 127)},
    "lfo_multiplier": {"type": "nrpn", "msb": LFOParams.MSB, "lsb": LFOParams.MULTIPLIER, "range": (0, 127)},
    "lfo_fade": {"type": "nrpn", "msb": LFOParams.MSB, "lsb": LFOParams.FADE, "range": (0, 127)},
    "lfo_destination": {"type": "nrpn", "msb": LFOParams.MSB, "lsb": LFOParams.DESTINATION, "range": (0, 127)},
    "lfo_waveform": {"type": "nrpn", "msb": LFOParams.MSB, "lsb": LFOParams.WAVEFORM, "range": (0, 127)},
    "lfo_start_phase": {"type": "nrpn", "msb": LFOParams.MSB, "lsb": LFOParams.START_PHASE, "range": (0, 127)},
    "lfo_trig_mode": {"type": "nrpn", "msb": LFOParams.MSB, "lsb": LFOParams.TRIG_MODE, "range": (0, 127)},
    "lfo_depth": {"type": "nrpn", "msb": LFOParams.MSB, "lsb": LFOParams.DEPTH, "range": (0, 127)},

    # Aliases with "lfo1_" prefix for compatibility
    "lfo1_speed": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.SPEED, "range": (0, 127)},
    "lfo1_multiplier": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.MULTIPLIER, "range": (0, 127)},
    "lfo1_fade": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.FADE, "range": (0, 127)},
    "lfo1_destination": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.DESTINATION, "range": (0, 127)},
    "lfo1_waveform": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.WAVEFORM, "range": (0, 127)},
    "lfo1_start_phase": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.START_PHASE, "range": (0, 127)},
    "lfo1_trig_mode": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.TRIG_MODE, "range": (0, 127)},
    "lfo1_depth": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.DEPTH, "range": (0, 127)},

    # FX SEND PARAMETERS - Note: Delay/Reverb sends are in AMP on Digitakt 1
    "delay_send": {"type": "cc", "cc": FXCC.DELAY_SEND, "range": (0, 127)},    # CC 82
    "reverb_send": {"type": "cc", "cc": FXCC.REVERB_SEND, "range": (0, 127)},  # CC 83
    # No Chorus on Digitakt 1!

    # DELAY FX PARAMETERS
    "delay_time": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.TIME, "range": (0, 127)},
    "delay_pingpong": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.PINGPONG, "range": (0, 127)},
    "delay_stereo_width": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.STEREO_WIDTH, "range": (0, 127)},
    "delay_feedback": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.FEEDBACK, "range": (0, 127)},
    "delay_hpf": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.HPF, "range": (0, 127)},
    "delay_lpf": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.LPF, "range": (0, 127)},
    "delay_reverb_send": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.REVERB_SEND, "range": (0, 127)},
    "delay_mix": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.MIX, "range": (0, 127)},

    # REVERB FX PARAMETERS
    "reverb_predelay": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.PREDELAY, "range": (0, 127)},
    "reverb_decay": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.DECAY, "range": (0, 127)},
    "reverb_shelving_freq": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.SHELVING_FREQ, "range": (0, 127)},
    "reverb_shelving_gain": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.SHELVING_GAIN, "range": (0, 127)},
    "reverb_hpf": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.HPF, "range": (0, 127)},
    "reverb_lpf": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.LPF, "range": (0, 127)},
    "reverb_mix": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.MIX, "range": (0, 127)},

    # TRACK PARAMETERS
    "track_level": {"type": "cc", "cc": TrackCC.LEVEL, "range": (0, 127)},
    "track_mute": {"type": "cc", "cc": TrackCC.MUTE, "range": (0, 127)},
    "track_solo": {"type": "cc", "cc": TrackCC.SOLO, "range": (0, 127)},

    # TRIG PARAMETERS (for currently selected trig)
    "trig_note": {"type": "nrpn", "msb": TrigParams.MSB, "lsb": TrigParams.NOTE, "range": (0, 127)},
    "trig_velocity": {"type": "nrpn", "msb": TrigParams.MSB, "lsb": TrigParams.VELOCITY, "range": (0, 127)},
    "trig_length": {"type": "nrpn", "msb": TrigParams.MSB, "lsb": TrigParams.LENGTH, "range": (0, 127)},
}


def validate_parameter(param_name: str, value: int) -> tuple[bool, str]:
    """
    Validate a parameter name and value
    Returns: (is_valid, error_message)
    """
    if param_name not in PARAMETER_MAP:
        available = ", ".join(sorted(PARAMETER_MAP.keys()))
        return False, f"Unknown parameter '{param_name}'. Available parameters: {available}"

    param_info = PARAMETER_MAP[param_name]
    min_val, max_val = param_info["range"]

    if not (min_val <= value <= max_val):
        return False, f"Value {value} out of range for '{param_name}' (valid range: {min_val}-{max_val})"

    return True, ""


def get_parameter_info(param_name: str) -> dict:
    """Get parameter mapping info"""
    return PARAMETER_MAP.get(param_name)


def get_all_parameters() -> list[str]:
    """Get list of all available parameter names"""
    return sorted(PARAMETER_MAP.keys())


def get_parameters_by_category() -> dict:
    """Get parameters organized by category"""
    categories = {
        "Filter": [],
        "Filter Envelope": [],
        "Amp": [],
        "Amp Envelope": [],
        "Source/Sample": [],
        "LFO": [],  # Only 1 LFO on Digitakt 1
        "FX Sends": [],
        "Delay FX": [],
        "Reverb FX": [],
        "Track": [],
        "Trig": [],
    }

    for param_name in PARAMETER_MAP.keys():
        if param_name.startswith("filter_") and not any(x in param_name for x in ["attack", "decay", "sustain", "release", "env"]):
            categories["Filter"].append(param_name)
        elif param_name.startswith("filter_") and any(x in param_name for x in ["attack", "decay", "sustain", "release", "env"]):
            categories["Filter Envelope"].append(param_name)
        elif param_name.startswith("amp_") and not any(x in param_name for x in ["attack", "hold", "decay", "sustain", "release", "env", "mode"]):
            categories["Amp"].append(param_name)
        elif param_name.startswith("amp_") and any(x in param_name for x in ["attack", "hold", "decay", "sustain", "release", "env", "mode", "overdrive"]):
            categories["Amp Envelope"].append(param_name)
        elif param_name.startswith("lfo"):
            categories["LFO"].append(param_name)
        elif param_name in ["delay_send", "reverb_send", "overdrive"]:
            categories["FX Sends"].append(param_name)
        elif param_name.startswith("delay_"):
            categories["Delay FX"].append(param_name)
        elif param_name.startswith("reverb_"):
            categories["Reverb FX"].append(param_name)
        elif param_name.startswith("track_"):
            categories["Track"].append(param_name)
        elif param_name.startswith("trig_"):
            categories["Trig"].append(param_name)
        elif param_name in ["tune", "pitch", "bit_reduction", "play_mode", "sample_slot", "sample_start", "sample_length", "sample_loop", "sample_level"]:
            categories["Source/Sample"].append(param_name)
        elif param_name in ["volume", "pan"]:
            categories["Amp"].append(param_name)

    # Remove empty categories
    return {k: sorted(v) for k, v in categories.items() if v}
