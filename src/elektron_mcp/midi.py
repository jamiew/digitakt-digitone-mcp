"""MIDI connection and message sending.

The old servers kept `output_port` / `input_port` as module globals, which is the
main reason the two device servers had to be copy-pasted rather than shared: every
tool closed over its own module's globals. Holding them on an object instead is
what lets one set of tools serve any device.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import mido

# mido ships no py.typed and builds its port helpers dynamically, so the type
# checker can't see them. The `ty: ignore` comments below are all for that.

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# NRPN is four CCs: parameter MSB, parameter LSB, then data entry MSB/LSB.
CC_NRPN_MSB = 99
CC_NRPN_LSB = 98
CC_DATA_ENTRY_MSB = 6
CC_DATA_ENTRY_LSB = 38


def note_name(note: int) -> str:
    """MIDI note number to name, e.g. 60 -> C4."""
    return f"{NOTE_NAMES[note % 12]}{(note // 12) - 1}"


class NotConnectedError(RuntimeError):
    """Raised when a tool needs a port that isn't open."""


@dataclass
class MidiConnection:
    """An open (or not-yet-open) pair of MIDI ports for one device."""

    port_name: str
    display_name: str
    logger: logging.Logger
    output_port: mido.ports.BaseOutput | None = None
    input_port: mido.ports.BaseInput | None = None

    # ---------------------------------------------------------------- lifecycle

    def connect(self) -> None:
        """Open the first in/out ports whose names contain `port_name`.

        Never raises: a missing device logs a warning and leaves the ports None so
        the server still starts and tools can report a useful error.
        """
        try:
            for name in mido.get_output_names():  # ty: ignore[unresolved-attribute]
                if self.port_name in name:
                    self.output_port = mido.open_output(name)  # ty: ignore[unresolved-attribute]
                    self.logger.info(f"Connected to MIDI output: {name}")
                    break
            else:
                self.logger.warning(f"Could not find MIDI output port for {self.port_name}")

            for name in mido.get_input_names():  # ty: ignore[unresolved-attribute]
                if self.port_name in name:
                    self.input_port = mido.open_input(name)  # ty: ignore[unresolved-attribute]
                    self.logger.info(f"Connected to MIDI input: {name}")
                    break
            else:
                self.logger.warning(f"Could not find MIDI input port for {self.port_name}")

        except Exception as exc:
            self.logger.error(f"Error connecting to MIDI: {exc}")

    def close(self) -> None:
        for port in (self.output_port, self.input_port):
            if port is not None:
                port.close()
        self.output_port = None
        self.input_port = None

    @property
    def is_connected(self) -> bool:
        return self.output_port is not None

    def require_output(self) -> mido.ports.BaseOutput:
        if self.output_port is None:
            raise NotConnectedError(
                f"Not connected to {self.display_name} MIDI output. "
                f"Check the device is powered on and USB/MIDI connected, then restart the server."
            )
        return self.output_port

    def require_input(self) -> mido.ports.BaseInput:
        if self.input_port is None:
            raise NotConnectedError(
                f"Not connected to {self.display_name} MIDI input. "
                f"Check the device is powered on and USB/MIDI connected, then restart the server."
            )
        return self.input_port

    # ----------------------------------------------------------------- sending

    def send(self, message: mido.Message) -> None:
        self.require_output().send(message)

    def note_on(self, note: int, velocity: int, channel: int) -> None:
        self.send(mido.Message("note_on", note=note, velocity=velocity, channel=channel))

    def note_off(self, note: int, channel: int) -> None:
        self.send(mido.Message("note_off", note=note, velocity=0, channel=channel))

    def cc(self, control: int, value: int, channel: int) -> None:
        self.send(mido.Message("control_change", control=control, value=value, channel=channel))

    def nrpn(self, msb: int, lsb: int, value: int, channel: int, data_lsb: int = 0) -> None:
        """Send a 4-message NRPN. `data_lsb` carries the low 7 bits of 14-bit values."""
        self.cc(CC_NRPN_MSB, msb, channel)
        self.cc(CC_NRPN_LSB, lsb, channel)
        self.cc(CC_DATA_ENTRY_MSB, value, channel)
        self.cc(CC_DATA_ENTRY_LSB, data_lsb, channel)

    def nrpn_14bit(self, msb: int, lsb: int, value: int, channel: int) -> None:
        """Send a 14-bit NRPN value (0-16383), split across data entry MSB/LSB."""
        self.nrpn(msb, lsb, (value >> 7) & 0x7F, channel, data_lsb=value & 0x7F)

    async def note_off_after(self, note: int, duration: float, channel: int) -> None:
        await asyncio.sleep(duration)
        if self.output_port is not None:
            self.output_port.send(mido.Message("note_off", note=note, velocity=0, channel=channel))

    # ----------------------------------------------------------------- logging

    def log_cc(self, control: int, value: int, channel: int, name: str | None = None) -> None:
        suffix = f"  ({name})" if name else ""
        self.logger.info(f"🎛️  CC {control:3d} = {value:3d}  ch={channel + 1}{suffix}")

    def log_nrpn(self, msb: int, lsb: int, value: int, channel: int, name: str | None = None) -> None:
        suffix = f"  ({name})" if name else ""
        self.logger.info(f"🎚️  NRPN {msb}:{lsb} = {value:3d}  ch={channel + 1}{suffix}")

    def log_transport(self, kind: str) -> None:
        self.logger.info(f"🚀 TRANSPORT: {kind}")

    def log_program_change(self, program: int, channel: int) -> None:
        self.logger.info(f"📀 PROGRAM CHANGE: {program}  ch={channel + 1}")

    def log_sysex(self, data: list[int]) -> None:
        display = " ".join(f"{b:02X}" for b in data[:16])
        if len(data) > 16:
            display += f"... ({len(data)} bytes)"
        self.logger.info(f"📡 SYSEX: F0 {display} F7")


def available_ports() -> dict[str, list[str]]:
    inputs = mido.get_input_names()  # ty: ignore[unresolved-attribute]
    outputs = mido.get_output_names()  # ty: ignore[unresolved-attribute]
    return {"inputs": list(inputs), "outputs": list(outputs)}
