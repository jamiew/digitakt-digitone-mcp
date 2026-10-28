"""Device storage through `elektroid-cli`: the +Drive, the project's sample slots, sounds.

MIDI alone can't see storage. Elektroid (https://github.com/dagargo/elektroid) speaks
Elektron's SysEx file protocol over the same USB port, so this shells out to its CLI
and parses what it prints. Keep the surface small so a native SysEx backend can
replace it without touching the tools.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

BINARY = "elektroid-cli"
INSTALL_HINT = "Install Elektroid (https://github.com/dagargo/elektroid), which provides elektroid-cli."

Runner = Callable[[list[str], float], Awaitable[str]]
"""Runs `elektroid-cli <args>` with a timeout in seconds and returns its stdout."""


class ElektroidError(ToolError):
    """elektroid-cli is missing, can't find the device, or a command failed."""


@dataclass(frozen=True, slots=True)
class DriveEntry:
    name: str
    is_dir: bool
    size: str


@dataclass(frozen=True, slots=True)
class Slot:
    number: int
    path: str | None
    size: str
    used: bool
    """Some pattern in the project plays it."""


@dataclass(frozen=True, slots=True)
class TrackSample:
    track: int
    slot: int | None
    path: str | None


@dataclass(frozen=True, slots=True)
class Sound:
    index: int
    name: str


# `elektroid-cli ld`: "1: id: Elektron Digitakt :: Elektron Digitakt; name: ..."
_DEVICE = re.compile(r"^(\d+): id: (.*?); name: (.*)$")
# sample:ls: "F   46.55KiB 776255e5 Kick 01" / "D         0B 00000000 breaks"
_DRIVE = re.compile(r"^([FD])\s+(\S+)\s+[0-9a-f]{8} (.+?)\s*$")
# ram:ls: "F   140.7KiB          1        001 /factory/.../BD Digit [ used ]", empty slots end after the index
_SLOT = re.compile(r"^F\s+(\S+)\s+(\d+)\s+\d{3}\s*(.*?)\s*$")
# track:ls: "F  ?B  0  000 1   [ slot=16:path=/D&P onehits selected/Kick/Kick 05 ]"
_TRACK = re.compile(r"^F\s+\S+\s+\d+\s+\d{3} (\d+)\s*(?:\[ slot=(\d+):path=(.*) \])?\s*$")
# data:ls: "F 0012 1 1       160B        001 SNARE JAY"
_SOUND = re.compile(r"^F\s+\S+\s+\d+\s+\d+\s+\S+\s+(\d{3}) (.+?)\s*$")
_USED = "[ used ]"


def parse_devices(text: str) -> dict[int, str]:
    return {int(m[1]): m[3] for line in text.splitlines() if (m := _DEVICE.match(line.strip()))}


def parse_drive(text: str) -> list[DriveEntry]:
    return [DriveEntry(m[3], m[1] == "D", m[2]) for line in text.splitlines() if (m := _DRIVE.match(line))]


def parse_slots(text: str) -> list[Slot]:
    slots = []
    for line in text.splitlines():
        if not (m := _SLOT.match(line)):
            continue
        used = m[3].endswith(_USED)
        rest = m[3].removesuffix(_USED).rstrip()
        slots.append(Slot(int(m[2]), rest or None, m[1], used))
    return slots


def parse_tracks(text: str) -> list[TrackSample]:
    return [
        TrackSample(int(m[1]), int(m[2]) if m[2] else None, m[3])
        for line in text.splitlines()
        if (m := _TRACK.match(line))
    ]


def parse_sounds(text: str) -> list[Sound]:
    return [Sound(int(m[1]), m[2]) for line in text.splitlines() if (m := _SOUND.match(line))]


async def run_cli(args: list[str], timeout: float) -> str:
    binary = shutil.which(BINARY)
    if binary is None:
        raise ElektroidError(f"{BINARY} not found. {INSTALL_HINT}")
    process = await asyncio.create_subprocess_exec(
        binary, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError as exc:
        process.kill()
        raise ElektroidError(f"{BINARY} {' '.join(args)} timed out after {timeout:.0f}s") from exc
    if process.returncode != 0:
        detail = (stderr or stdout).decode(errors="replace").strip().splitlines()
        raise ElektroidError(f"{BINARY} {' '.join(args)} failed: {detail[-1] if detail else process.returncode}")
    return stdout.decode(errors="replace")


class Elektroid:
    """One device's storage, found by the same port name the MIDI connection uses."""

    def __init__(self, port_name: str, runner: Runner = run_cli) -> None:
        self.port_name = port_name
        self._run = runner
        self._number: int | None = None
        # One SysEx transfer at a time; interleaved requests confuse the device.
        self._lock = asyncio.Lock()

    async def _cli(self, *args: str, timeout: float = 60) -> str:
        async with self._lock:
            return await self._run(list(args), timeout)

    async def device(self) -> int:
        """elektroid's device number, which shifts with whatever else is plugged in."""
        if self._number is None:
            devices = parse_devices(await self._cli("ld"))
            matches = [n for n, name in devices.items() if self.port_name in name]
            if not matches:
                raise ElektroidError(f"elektroid-cli can't see an {self.port_name}. Is it on USB?")
            self._number = matches[0]
        return self._number

    async def _at(self, path: str) -> str:
        return f"{await self.device()}:{path}"

    async def usage(self) -> str:
        return (await self._cli("df", f"{await self.device()}:/")).strip()

    async def list_drive(self, path: str) -> list[DriveEntry]:
        return parse_drive(await self._cli("elektron:sample:ls", await self._at(path)))

    async def slots(self) -> list[Slot]:
        return parse_slots(await self._cli("elektron:ram:ls", await self._at("/")))

    async def tracks(self) -> list[TrackSample]:
        return parse_tracks(await self._cli("elektron:track:ls", await self._at("/")))

    async def sounds(self, bank: str) -> list[Sound]:
        return parse_sounds(await self._cli("elektron:data:ls", await self._at(f"/soundbanks/{bank}")))

    async def download(self, drive_path: str, destination: Path) -> Path:
        """Copy a +Drive sample to `destination` (a directory) and return the local WAV."""
        before = set(destination.glob("*.wav"))
        await self._cli("elektron:sample:dl", await self._at(drive_path), str(destination), timeout=300)
        new = sorted(set(destination.glob("*.wav")) - before)
        if not new:
            raise ElektroidError(f"Downloaded {drive_path} but no WAV appeared in {destination}")
        return new[0]

    async def upload(self, local: Path, drive_dir: str) -> None:
        await self._cli("elektron:sample:mkdir", await self._at(drive_dir))
        await self._cli("elektron:sample:ul", str(local), await self._at(drive_dir), timeout=600)

    async def load_into_slot(self, local: Path, slot: int) -> None:
        """Put a local WAV in a RAM slot. Elektroid copies it to /incoming on the +Drive first."""
        await self._cli("elektron:ram:ul", str(local), await self._at(f"/{slot}"), timeout=600)
