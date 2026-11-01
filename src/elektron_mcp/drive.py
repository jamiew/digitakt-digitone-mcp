"""MCP tools for device storage: the +Drive, sample slots and sounds, via elektroid.

Reads are safe. Loading changes which sample a track plays, like turning the knob.
Anything coming from outside the project's slots is uploaded, and elektroid parks a
copy in /incoming on the +Drive. Nothing here deletes from the +Drive.
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from elektron_mcp.elektroid import Slot
from elektron_mcp.kit import DEFAULT_KIT, ROLES, pick_kit
from elektron_mcp.server import LISTENS, DeviceServer

LOADS = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True)
"""Changes a track's sample, and may upload to the +Drive."""
UPLOADS = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True)
"""Writes files to the +Drive; a file with the same name is replaced."""

SLOT_COUNT = 127
AUDIO = {".wav", ".aif", ".aiff"}
MAX_UPLOADS = 128
MAX_LISTED = 200

Track = Annotated[int, Field(ge=1, le=8, description="Audio track (1-8).")]


def register_sound_tools(device: DeviceServer) -> None:
    """Sound pools exist on both machines."""

    @device.tool(LISTENS)
    async def list_sounds(
        bank: Annotated[str, Field(pattern="^[A-P]$", description="Sound bank letter on the +Drive.")] = "A",
    ) -> str:
        """List the saved sounds in one +Drive sound bank (needs elektroid-cli)."""
        sounds = await device.elektroid.sounds(bank)
        if not sounds:
            return f"Bank {bank} is empty."
        return f"Bank {bank} ({len(sounds)} sounds):\n" + "\n".join(f"{s.index:3d} {s.name}" for s in sounds)


def _slot_line(slot: Slot) -> str:
    return f"{slot.number:3d} {slot.path or '(empty)'}{'  [used]' if slot.used else ''}"


def register_sample_tools(device: DeviceServer) -> None:
    """The Digitakt's +Drive, its project sample slots, and what each track plays."""
    sample_slot = device.resolve("sample_slot")

    def set_track_slot(track: int, slot: int) -> None:
        device.apply(sample_slot, slot, track - 1)

    async def check_tracks(expected: dict[int, int]) -> str:
        """Read the tracks back. A CC on the AUTO channel lands on the active track instead."""
        actual = {t.track: t.slot for t in await device.elektroid.tracks()}
        missed = sorted(t for t, slot in expected.items() if actual.get(t) != slot)
        if not missed:
            return ""
        return (
            f"\nWarning: track(s) {', '.join(map(str, missed))} didn't change. Their MIDI channel is probably "
            "also the AUTO channel, which controls the active track instead. Check Settings > MIDI > Channels."
        )

    async def upload_to_free_slot(local: Path) -> int:
        slots = await device.elektroid.slots()
        free = next((s.number for s in slots if s.path is None), None)
        if free is None:
            raise ToolError("All 127 sample slots are full. Free one on the device first.")
        await device.elektroid.load_into_slot(local, free)
        return free

    @device.tool(LISTENS)
    async def list_drive(
        path: Annotated[str, Field(description="+Drive folder, e.g. '/' or '/drums/Kicks'.")] = "/",
    ) -> str:
        """List a +Drive folder, with storage usage (needs elektroid-cli)."""
        entries = await device.elektroid.list_drive(path)
        usage = await device.elektroid.usage()
        lines = [f"{e.name}/" if e.is_dir else f"{e.name}  ({e.size})" for e in entries[:MAX_LISTED]]
        if len(entries) > MAX_LISTED:
            lines.append(f"… {len(entries) - MAX_LISTED} more")
        return f"{path}\n" + ("\n".join(lines) or "(empty)") + f"\n\n{usage}"

    @device.tool(LISTENS)
    async def list_sample_slots(
        query: Annotated[str | None, Field(description="Only slots whose path contains this, e.g. 'kick'.")] = None,
        include_empty: Annotated[bool, Field(description="Also list empty slots.")] = False,
    ) -> str:
        """Show which slot each track plays, then the project's sample slots (needs elektroid-cli)."""
        tracks = await device.elektroid.tracks()
        slots = await device.elektroid.slots()
        lines = ["Tracks:"]
        lines += [f"  {t.track}: slot {t.slot} {t.path}" if t.slot else f"  {t.track}: (none)" for t in tracks]

        shown = [s for s in slots if include_empty or s.path]
        if query:
            shown = [s for s in shown if s.path and query.lower() in s.path.lower()]
        free = sum(1 for s in slots if s.path is None)
        lines += ["", f"Slots ({len(shown)} shown, {free} empty):"] + [f"  {_slot_line(s)}" for s in shown]
        return "\n".join(lines)

    @device.tool(LOADS)
    async def load_sample(
        track: Track,
        sample: Annotated[
            int | str,
            Field(description="A slot number (17), a +Drive path ('/drums/Kicks/Kick 01') or a local WAV path."),
        ],
    ) -> str:
        """Make a track play a sample. Slots switch instantly; anything else is uploaded into a free slot first."""
        slots = await device.elektroid.slots()
        note = ""
        sample = str(sample).strip()

        if sample.isdigit():
            slot = int(sample)
            match = next((s for s in slots if s.number == slot), None)
            if match is None or match.path is None:
                raise ToolError(f"Slot {slot} is empty. Use list_sample_slots to see what's loaded.")
            path = match.path
        elif (local := Path(sample).expanduser()).is_file():
            slot = await upload_to_free_slot(local)
            path, note = str(local), " Uploaded it; elektroid keeps a copy in /incoming on the +Drive."
        elif sample.startswith("/"):
            path = sample.rstrip("/")
            loaded = {s.path: s.number for s in slots if s.path}
            stem = path.rsplit(".", 1)[0]
            if path in loaded or stem in loaded:
                slot = loaded.get(path) or loaded[stem]
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    wav = await device.elektroid.download(path, Path(tmp))
                    slot = await upload_to_free_slot(wav)
                note = " It wasn't in the project yet, so a copy now also sits in /incoming on the +Drive."
        else:
            raise ToolError(f"{sample!r} isn't a slot number, a +Drive path starting with '/', or a local file.")

        set_track_slot(track, slot)
        return f"Track {track} now plays slot {slot}: {path}.{note}" + await check_tracks({track: slot})

    @device.tool(UPLOADS)
    async def upload_samples(
        local_path: Annotated[str, Field(description="A WAV/AIFF file, or a folder of them (subfolders are kept).")],
        drive_folder: Annotated[str, Field(description="+Drive folder to upload into, e.g. '/cipher/atoll'.")],
    ) -> str:
        """Copy samples from this computer onto the +Drive (needs elektroid-cli). Doesn't load them onto tracks."""
        source = Path(local_path).expanduser()
        if source.is_file():
            files = [source]
            root = source.parent
        elif source.is_dir():
            files = sorted(p for p in source.rglob("*") if p.suffix.lower() in AUDIO)
            root = source
        else:
            raise ToolError(f"No such file or folder: {source}")
        if not files:
            raise ToolError(f"No WAV or AIFF files in {source}")
        if len(files) > MAX_UPLOADS:
            raise ToolError(f"{len(files)} files is more than {MAX_UPLOADS} at once. Pick a smaller folder.")

        base = "/" + drive_folder.strip("/")
        uploaded = []
        for file in files:
            folder = "/".join(filter(None, [base.rstrip("/"), *file.parent.relative_to(root).parts])) or "/"
            await device.elektroid.upload(file, folder)
            uploaded.append(f"{folder}/{file.stem}")
        return f"Uploaded {len(uploaded)} files:\n" + "\n".join(uploaded)

    @device.tool(LOADS)
    async def bootstrap_kit(
        roles: Annotated[
            dict[str, str] | None,
            Field(
                description=f"Track -> role, e.g. {{'1': 'kick'}}. Roles: {', '.join(ROLES)}. Default: {DEFAULT_KIT}."
            ),
        ] = None,
        seed: Annotated[int | None, Field(description="Random seed, to repeat a pick.")] = None,
        dry_run: Annotated[bool, Field(description="Show the picks without changing any track.")] = False,
    ) -> str:
        """Pick a sample per role at random from the project's slots and put each on its track.

        Prefers slots no pattern uses yet. Only switches slots, so nothing is uploaded.
        """
        wanted = {int(t): r for t, r in roles.items()} if roles else dict(DEFAULT_KIT)
        bad = {t: r for t, r in wanted.items() if r not in ROLES or not 1 <= t <= 8}
        if bad:
            raise ToolError(f"Unknown tracks or roles: {bad}. Tracks are 1-8; roles are {', '.join(ROLES)}.")

        before = {t.track: t.slot for t in await device.elektroid.tracks()}
        picks = pick_kit(await device.elektroid.slots(), wanted, random.Random(seed))

        lines = []
        applied: dict[int, int] = {}
        for track, slot in sorted(picks.items()):
            role = wanted[track]
            if slot is None:
                lines.append(f"track {track} {role}: nothing in the slots looks like a {role}; try list_drive")
                continue
            if not dry_run:
                set_track_slot(track, slot.number)
                applied[track] = slot.number
            lines.append(f"track {track} {role}: slot {slot.number} {slot.path} (was slot {before.get(track)})")
        verb = "Would set" if dry_run else "Set"
        return f"{verb}:\n" + "\n".join(lines) + (await check_tracks(applied) if applied else "")

    @device.mcp.resource(f"midi://{device.spec.slug}/kit", mime_type="application/json")
    async def kit() -> str:
        """Each track's sample slot and the project's slots, as JSON (needs elektroid-cli)."""
        tracks = await device.elektroid.tracks()
        slots = await device.elektroid.slots()
        return json.dumps(
            {
                "tracks": [{"track": t.track, "slot": t.slot, "path": t.path} for t in tracks],
                "slots": [{"slot": s.number, "path": s.path, "used": s.used} for s in slots if s.path],
            },
            indent=2,
        )
