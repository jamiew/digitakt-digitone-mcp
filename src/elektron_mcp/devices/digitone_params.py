"""
Digitone (original) Parameter Mapping for Automation
Maps human-readable parameter names to MIDI CC/NRPN messages.

Key differences from Digitakt:
- FM synthesis params (algorithm, ratios, operator envelopes) instead of sample params
- 2 LFOs instead of 1
- Chorus effect (Digitakt has none)
- Different CC numbers for filter, amp, etc.
"""

from elektron_mcp.devices.digitone_cc import (
    AmpCC,
    ChorusParams,
    DelayParams,
    FilterCC,
    LFO1Params,
    LFO2Params,
    ReverbParams,
    Syn1CC,
    Syn2CC,
    TrackCC,
    TrigParams,
)

PARAMETER_MAP = {
    # FM SYNTHESIS - SYN1
    "fm_algorithm": {"type": "cc", "cc": Syn1CC.ALGORITHM, "range": (0, 7)},
    "fm_ratio_c": {"type": "cc", "cc": Syn1CC.RATIO_C, "range": (0, 127)},
    "fm_ratio_a": {"type": "cc", "cc": Syn1CC.RATIO_A, "range": (0, 127)},
    "fm_ratio_b": {"type": "cc", "cc": Syn1CC.RATIO_B_MSB, "range": (0, 127)},
    "fm_harmonics": {"type": "cc", "cc": Syn1CC.HARMONICS_MSB, "range": (0, 127)},
    "fm_detune": {"type": "cc", "cc": Syn1CC.DETUNE_MSB, "range": (0, 127)},
    "fm_feedback": {"type": "cc", "cc": Syn1CC.FEEDBACK_MSB, "range": (0, 127)},
    "fm_mix": {"type": "cc", "cc": Syn1CC.MIX_MSB, "range": (0, 127)},
    # FM SYNTHESIS - SYN2 (Operator Envelopes)
    "op_a_attack": {"type": "cc", "cc": Syn2CC.A_ENV_ATTACK, "range": (0, 127)},
    "op_a_decay": {"type": "cc", "cc": Syn2CC.A_ENV_DECAY, "range": (0, 127)},
    "op_a_end": {"type": "cc", "cc": Syn2CC.A_ENV_END, "range": (0, 127)},
    "op_a_level": {"type": "cc", "cc": Syn2CC.A_LEVEL, "range": (0, 127)},
    "op_b_attack": {"type": "cc", "cc": Syn2CC.B_ENV_ATTACK, "range": (0, 127)},
    "op_b_decay": {"type": "cc", "cc": Syn2CC.B_ENV_DECAY, "range": (0, 127)},
    "op_b_end": {"type": "cc", "cc": Syn2CC.B_ENV_END, "range": (0, 127)},
    "op_b_level": {"type": "cc", "cc": Syn2CC.B_LEVEL, "range": (0, 127)},
    "op_a_delay": {"type": "cc", "cc": Syn2CC.A_DELAY, "range": (0, 127)},
    "op_a_trig": {"type": "cc", "cc": Syn2CC.A_TRIG, "range": (0, 127)},
    "op_a_env_reset": {"type": "cc", "cc": Syn2CC.A_ENV_RESET, "range": (0, 127)},
    "op_b_delay": {"type": "cc", "cc": Syn2CC.B_DELAY, "range": (0, 127)},
    "op_b_trig": {"type": "cc", "cc": Syn2CC.B_TRIG, "range": (0, 127)},
    "op_b_env_reset": {"type": "cc", "cc": Syn2CC.B_ENV_RESET, "range": (0, 127)},
    "phase_reset": {"type": "cc", "cc": Syn2CC.PHASE_RESET, "range": (0, 127)},
    # FILTER
    "filter_frequency": {"type": "cc", "cc": FilterCC.FREQUENCY_MSB, "range": (0, 127)},
    "filter_cutoff": {"type": "cc", "cc": FilterCC.FREQUENCY_MSB, "range": (0, 127)},
    "filter_resonance": {"type": "cc", "cc": FilterCC.RESONANCE_MSB, "range": (0, 127)},
    "filter_type": {"type": "cc", "cc": FilterCC.TYPE, "range": (0, 127)},
    "filter_attack": {"type": "cc", "cc": FilterCC.ENV_ATTACK, "range": (0, 127)},
    "filter_decay": {"type": "cc", "cc": FilterCC.ENV_DECAY, "range": (0, 127)},
    "filter_sustain": {"type": "cc", "cc": FilterCC.ENV_SUSTAIN, "range": (0, 127)},
    "filter_release": {"type": "cc", "cc": FilterCC.ENV_RELEASE, "range": (0, 127)},
    "filter_env_depth": {"type": "cc", "cc": FilterCC.ENV_DEPTH_MSB, "range": (0, 127)},
    "filter_env_delay": {"type": "cc", "cc": FilterCC.ENV_DELAY, "range": (0, 127)},
    "filter_base": {"type": "cc", "cc": FilterCC.BASE_MSB, "range": (0, 127)},
    "filter_width": {"type": "cc", "cc": FilterCC.WIDTH_MSB, "range": (0, 127)},
    # AMP
    "amp_attack": {"type": "cc", "cc": AmpCC.ATTACK, "range": (0, 127)},
    "amp_decay": {"type": "cc", "cc": AmpCC.DECAY, "range": (0, 127)},
    "amp_sustain": {"type": "cc", "cc": AmpCC.SUSTAIN, "range": (0, 127)},
    "amp_release": {"type": "cc", "cc": AmpCC.RELEASE, "range": (0, 127)},
    "amp_drive": {"type": "cc", "cc": AmpCC.DRIVE_MSB, "range": (0, 127)},
    "amp_pan": {"type": "cc", "cc": AmpCC.PAN_MSB, "range": (0, 127)},
    "amp_volume": {"type": "cc", "cc": AmpCC.VOLUME_MSB, "range": (0, 127)},
    "volume": {"type": "cc", "cc": AmpCC.VOLUME_MSB, "range": (0, 127)},
    "pan": {"type": "cc", "cc": AmpCC.PAN_MSB, "range": (0, 127)},
    "amp_chorus_send": {"type": "cc", "cc": AmpCC.CHORUS_SEND_MSB, "range": (0, 127)},
    "amp_delay_send": {"type": "cc", "cc": AmpCC.DELAY_SEND_MSB, "range": (0, 127)},
    "amp_reverb_send": {"type": "cc", "cc": AmpCC.REVERB_SEND_MSB, "range": (0, 127)},
    "chorus_send": {"type": "cc", "cc": AmpCC.CHORUS_SEND_MSB, "range": (0, 127)},
    "delay_send": {"type": "cc", "cc": AmpCC.DELAY_SEND_MSB, "range": (0, 127)},
    "reverb_send": {"type": "cc", "cc": AmpCC.REVERB_SEND_MSB, "range": (0, 127)},
    "amp_env_reset": {"type": "cc", "cc": AmpCC.ENV_RESET, "range": (0, 127)},
    # LFO 1
    "lfo1_speed": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.SPEED, "range": (0, 127)},
    "lfo1_multiplier": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.MULTIPLIER, "range": (0, 127)},
    "lfo1_fade": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.FADE, "range": (0, 127)},
    "lfo1_destination": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.DESTINATION, "range": (0, 127)},
    "lfo1_waveform": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.WAVEFORM, "range": (0, 127)},
    "lfo1_start_phase": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.START_PHASE, "range": (0, 127)},
    "lfo1_trig_mode": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.TRIG_MODE, "range": (0, 127)},
    "lfo1_depth": {"type": "nrpn", "msb": LFO1Params.MSB, "lsb": LFO1Params.DEPTH, "range": (0, 127)},
    # LFO 2
    "lfo2_speed": {"type": "nrpn", "msb": LFO2Params.MSB, "lsb": LFO2Params.SPEED, "range": (0, 127)},
    "lfo2_multiplier": {"type": "nrpn", "msb": LFO2Params.MSB, "lsb": LFO2Params.MULTIPLIER, "range": (0, 127)},
    "lfo2_fade": {"type": "nrpn", "msb": LFO2Params.MSB, "lsb": LFO2Params.FADE, "range": (0, 127)},
    "lfo2_destination": {"type": "nrpn", "msb": LFO2Params.MSB, "lsb": LFO2Params.DESTINATION, "range": (0, 127)},
    "lfo2_waveform": {"type": "nrpn", "msb": LFO2Params.MSB, "lsb": LFO2Params.WAVEFORM, "range": (0, 127)},
    "lfo2_start_phase": {"type": "nrpn", "msb": LFO2Params.MSB, "lsb": LFO2Params.START_PHASE, "range": (0, 127)},
    "lfo2_trig_mode": {"type": "nrpn", "msb": LFO2Params.MSB, "lsb": LFO2Params.TRIG_MODE, "range": (0, 127)},
    "lfo2_depth": {"type": "nrpn", "msb": LFO2Params.MSB, "lsb": LFO2Params.DEPTH, "range": (0, 127)},
    # NRPN-only ratio offsets (14-bit, ~2000 values)
    "fm_ratio_c_offset": {"type": "nrpn", "msb": 1, "lsb": 95, "range": (0, 16383)},
    "fm_ratio_a_offset": {"type": "nrpn", "msb": 1, "lsb": 96, "range": (0, 16383)},
    "fm_ratio_b1_offset": {"type": "nrpn", "msb": 1, "lsb": 97, "range": (0, 16383)},
    "fm_ratio_b2_offset": {"type": "nrpn", "msb": 1, "lsb": 98, "range": (0, 16383)},
    # CHORUS FX (on FX channel)
    "chorus_depth": {"type": "nrpn", "msb": ChorusParams.MSB, "lsb": ChorusParams.DEPTH, "range": (0, 127)},
    "chorus_speed": {"type": "nrpn", "msb": ChorusParams.MSB, "lsb": ChorusParams.SPEED, "range": (0, 127)},
    "chorus_hp": {"type": "nrpn", "msb": ChorusParams.MSB, "lsb": ChorusParams.HP, "range": (0, 127)},
    "chorus_width": {"type": "nrpn", "msb": ChorusParams.MSB, "lsb": ChorusParams.WIDTH, "range": (0, 127)},
    "chorus_delay_send": {"type": "nrpn", "msb": ChorusParams.MSB, "lsb": ChorusParams.DELAY_SEND, "range": (0, 127)},
    "chorus_reverb_send": {
        "type": "nrpn",
        "msb": ChorusParams.MSB,
        "lsb": ChorusParams.REVERB_SEND,
        "range": (0, 127),
    },
    "chorus_mix": {"type": "nrpn", "msb": ChorusParams.MSB, "lsb": ChorusParams.MIX, "range": (0, 127)},
    # DELAY FX (on FX channel)
    "delay_time": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.TIME, "range": (0, 127)},
    "delay_pingpong": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.PINGPONG, "range": (0, 127)},
    "delay_stereo_width": {
        "type": "nrpn",
        "msb": DelayParams.MSB,
        "lsb": DelayParams.STEREO_WIDTH,
        "range": (0, 127),
    },
    "delay_feedback": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.FEEDBACK, "range": (0, 127)},
    "delay_hpf": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.HPF, "range": (0, 127)},
    "delay_lpf": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.LPF, "range": (0, 127)},
    "delay_reverb_send": {
        "type": "nrpn",
        "msb": DelayParams.MSB,
        "lsb": DelayParams.REVERB_SEND,
        "range": (0, 127),
    },
    "delay_mix": {"type": "nrpn", "msb": DelayParams.MSB, "lsb": DelayParams.MIX, "range": (0, 127)},
    # REVERB FX (on FX channel)
    "reverb_predelay": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.PREDELAY, "range": (0, 127)},
    "reverb_decay": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.DECAY, "range": (0, 127)},
    "reverb_shelving_freq": {
        "type": "nrpn",
        "msb": ReverbParams.MSB,
        "lsb": ReverbParams.SHELVING_FREQ,
        "range": (0, 127),
    },
    "reverb_shelving_gain": {
        "type": "nrpn",
        "msb": ReverbParams.MSB,
        "lsb": ReverbParams.SHELVING_GAIN,
        "range": (0, 127),
    },
    "reverb_hpf": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.HPF, "range": (0, 127)},
    "reverb_lpf": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.LPF, "range": (0, 127)},
    "reverb_mix": {"type": "nrpn", "msb": ReverbParams.MSB, "lsb": ReverbParams.MIX, "range": (0, 127)},
    # TRACK
    "track_level": {"type": "cc", "cc": TrackCC.LEVEL, "range": (0, 127)},
    "track_mute": {"type": "cc", "cc": TrackCC.MUTE, "range": (0, 127)},
    # TRIG
    "trig_root": {"type": "nrpn", "msb": TrigParams.MSB, "lsb": TrigParams.ROOT_NOTE, "range": (0, 127)},
    "trig_velocity": {"type": "nrpn", "msb": TrigParams.MSB, "lsb": TrigParams.VELOCITY, "range": (0, 127)},
    "trig_length": {"type": "nrpn", "msb": TrigParams.MSB, "lsb": TrigParams.LENGTH, "range": (0, 127)},
    "trig_portamento_time": {
        "type": "nrpn",
        "msb": TrigParams.MSB,
        "lsb": TrigParams.PORTAMENTO_TIME,
        "range": (0, 127),
    },
    "trig_portamento_on": {
        "type": "nrpn",
        "msb": TrigParams.MSB,
        "lsb": TrigParams.PORTAMENTO_ON,
        "range": (0, 127),
    },
}


def get_parameters_by_category() -> dict[str, list[str]]:
    """Get parameters organized by category"""
    categories = {
        "FM Synthesis (SYN1)": [],
        "Operator Envelopes (SYN2)": [],
        "Filter": [],
        "Filter Envelope": [],
        "Amp": [],
        "Amp Envelope": [],
        "FX Sends": [],
        "LFO 1": [],
        "LFO 2": [],
        "Chorus FX": [],
        "Delay FX": [],
        "Reverb FX": [],
        "Track": [],
        "Trig": [],
    }

    for name in PARAMETER_MAP:
        if name.startswith("fm_"):
            categories["FM Synthesis (SYN1)"].append(name)
        elif name.startswith("op_") or name == "phase_reset":
            categories["Operator Envelopes (SYN2)"].append(name)
        elif name.startswith("filter_") and any(x in name for x in ["attack", "decay", "sustain", "release", "env"]):
            categories["Filter Envelope"].append(name)
        elif name.startswith("filter_"):
            categories["Filter"].append(name)
        elif name.startswith("amp_") and any(x in name for x in ["attack", "decay", "sustain", "release"]):
            categories["Amp Envelope"].append(name)
        elif name.startswith("amp_") and "send" in name:
            categories["FX Sends"].append(name)
        elif name.startswith("amp_") or name in ("volume", "pan"):
            categories["Amp"].append(name)
        elif name in ("chorus_send", "delay_send", "reverb_send"):
            categories["FX Sends"].append(name)
        elif name.startswith("lfo1_"):
            categories["LFO 1"].append(name)
        elif name.startswith("lfo2_"):
            categories["LFO 2"].append(name)
        elif name.startswith("chorus_"):
            categories["Chorus FX"].append(name)
        elif name.startswith("delay_"):
            categories["Delay FX"].append(name)
        elif name.startswith("reverb_"):
            categories["Reverb FX"].append(name)
        elif name.startswith("track_"):
            categories["Track"].append(name)
        elif name.startswith("trig_"):
            categories["Trig"].append(name)

    return {k: sorted(v) for k, v in categories.items() if v}
