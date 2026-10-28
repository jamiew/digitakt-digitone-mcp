"""Storage tools, against a fake elektroid-cli that replays output captured from a Digitakt."""

from pathlib import Path

import pytest

from conftest import ToolError
from elektron_mcp import elektroid
from elektron_mcp.elektroid import Elektroid, parse_slots, parse_tracks
from elektron_mcp.kit import role_of

SAMPLE_SLOT_CC = 19

LD = """\
0: id: SYSTEM_ID; name: m3max.local
1: id: Elektron Digitakt :: Elektron Digitakt; name: Elektron Digitakt :: Elektron Digitakt
2: id: volca-sample; name: KORG Volca Sample
"""
RAM = """\
F   140.7KiB          1        001 /factory/Drums/Electronic/Digit/BD Digit [ used ]
F   44.03KiB          2        002 /factory/Drums/Electronic/Digit/SD Digit [ used ]
F   70.81KiB          7        007 /factory/Drums/Electronic/Digit/OH Digit
F   53.24KiB          6        006 /factory/Drums/Electronic/Digit/HH Digit
F   162.1KiB         14        014 /D&P onehits selected/Crash/Crash 02
F   16.33KiB         16        016 /D&P onehits selected/Kick/Kick 05 [ used ]
F   46.55KiB         17        017 /D&P onehits selected/Kick/Kick 01
F   1.066MiB         26        026 /D&P Loops selected/Jungle Beat 14
F         ?B         29        029
F         ?B         30        030
"""
TRACKS = """\
F         ?B          0        000 1                                [ slot=16:path=/D&P onehits selected/Kick/Kick 05 ]
F         ?B          1        001 2                                [ slot=2:path=/factory/Drums/Electronic/Digit/SD Digit ]
F         ?B          2        002 3
"""
DRIVE = """\
D         0B 00000000 breaks
F   46.55KiB 776255e5 Kick 01
"""


class FakeCli:
    """Answers elektroid-cli commands from canned output and records what was run."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def __call__(self, args: list[str], timeout: float) -> str:
        self.calls.append(args)
        command = args[0]
        if command == "elektron:sample:dl":
            Path(args[2], "Kick 09.wav").write_bytes(b"RIFF")
        return {
            "ld": LD,
            "elektron:ram:ls": RAM,
            "elektron:track:ls": TRACKS,
            "elektron:sample:ls": DRIVE,
            "df": "+Drive  959.5MiB",
        }.get(command, "")

    def commands(self) -> list[str]:
        return [c[0] for c in self.calls if c[0] not in ("ld", "elektron:ram:ls", "elektron:track:ls")]


@pytest.fixture
def cli(digitakt) -> FakeCli:
    fake = FakeCli()
    digitakt.device.elektroid = Elektroid("Elektron Digitakt", runner=fake)
    return fake


def slot_changes(harness) -> list[tuple[int, int]]:
    """(track, slot) for every sample-slot CC sent."""
    return [(m.channel + 1, m.value) for m in harness.port.of_type("control_change") if m.control == SAMPLE_SLOT_CC]


class TestParsing:
    def test_slots_keep_used_flags_and_empty_slots(self):
        slots = {s.number: s for s in parse_slots(RAM)}

        assert slots[1].path == "/factory/Drums/Electronic/Digit/BD Digit" and slots[1].used
        assert slots[17].path == "/D&P onehits selected/Kick/Kick 01" and not slots[17].used
        assert slots[29].path is None

    def test_tracks_map_to_slots(self):
        tracks = parse_tracks(TRACKS)

        assert [(t.track, t.slot) for t in tracks] == [(1, 16), (2, 2), (3, None)]


class TestRoles:
    @pytest.mark.parametrize(
        ("path", "role"),
        [
            ("/D&P onehits selected/Kick/Kick 05", "kick"),
            ("/factory/Drums/Electronic/Digit/BD Digit", "kick"),
            ("/breaks/Gems From The Crates/Snares/AKT-SNR-A010_bip", "snare"),
            ("/D&P onehits selected/HiHat - Cymbals/309 hats1_007_wav", "closed hat"),
            ("/factory/Drums/Electronic/Digit/OH Digit", "open hat"),
            ("/D&P onehits selected/Crash/Crash 02", "crash"),
            ("/D&P Loops selected/Jungle Beat 14", "break"),
            ("/breaks/The Drum Broker - International Breaks 1/WATER", "break"),
            ("/D&P onehits selected/Kick/Kick & Hat", "kick"),
            ("/cipher/atoll 2026-10-19/Atoll/piano loop 4bar 123bpm 2", None),
        ],
    )
    def test_role_from_name_or_folder(self, path, role):
        assert role_of(path) == role


class TestBootstrapKit:
    async def test_dry_run_changes_nothing(self, digitakt, cli):
        result = await digitakt.call("bootstrap_kit", dry_run=True, seed=1)

        assert "Would set" in result
        assert slot_changes(digitakt) == []

    async def test_picks_fresh_slots_per_role(self, digitakt, cli):
        result = await digitakt.call("bootstrap_kit", roles={"1": "kick", "3": "break", "6": "closed hat"})

        # Kick 05 is used by a pattern, so the unused Kick 01 wins.
        assert sorted(slot_changes(digitakt)) == [(1, 17), (3, 26), (6, 6)]
        assert "was slot 16" in result

    async def test_reports_roles_it_cant_fill(self, digitakt, cli):
        result = await digitakt.call("bootstrap_kit", roles={"5": "cowbell"})

        assert "nothing in the slots looks like a cowbell" in result
        assert slot_changes(digitakt) == []

    async def test_rejects_unknown_roles(self, digitakt, cli):
        with pytest.raises(ToolError, match="Unknown tracks or roles"):
            await digitakt.call("bootstrap_kit", roles={"1": "theremin"})


class TestLoadSample:
    async def test_slot_number_switches_the_track(self, digitakt, cli):
        await digitakt.call("load_sample", track=4, sample="14")

        assert slot_changes(digitakt) == [(4, 14)]
        assert cli.commands() == []

    async def test_drive_path_already_in_the_project_needs_no_upload(self, digitakt, cli):
        await digitakt.call("load_sample", track=1, sample="/D&P onehits selected/Kick/Kick 01")

        assert slot_changes(digitakt) == [(1, 17)]
        assert cli.commands() == []

    async def test_other_drive_paths_go_through_a_free_slot(self, digitakt, cli):
        result = await digitakt.call("load_sample", track=1, sample="/drums/Kick 09")

        assert cli.commands() == ["elektron:sample:dl", "elektron:ram:ul"]
        upload = next(c for c in cli.calls if c[0] == "elektron:ram:ul")
        assert upload[-1] == "1:/29"  # the first empty slot
        assert slot_changes(digitakt) == [(1, 29)]
        assert "/incoming" in result

    async def test_empty_slot_is_an_error(self, digitakt, cli):
        with pytest.raises(ToolError, match="Slot 30 is empty"):
            await digitakt.call("load_sample", track=1, sample="30")

    async def test_confirms_the_change_by_reading_the_track_back(self, digitakt, cli):
        # The fake device already shows track 1 on slot 16.
        result = await digitakt.call("load_sample", track=1, sample=16)

        assert "Warning" not in result

    async def test_warns_when_the_track_did_not_change(self, digitakt, cli):
        """Seen on hardware: a CC on the AUTO channel moves the active track, not the one asked for."""
        result = await digitakt.call("load_sample", track=1, sample=17)

        assert "track(s) 1 didn't change" in result
        assert "AUTO channel" in result


class TestUpload:
    async def test_folder_upload_keeps_subfolders(self, digitakt, cli, tmp_path):
        (tmp_path / "Atoll").mkdir()
        (tmp_path / "Atoll" / "drum loop 2bar 89bpm.wav").write_bytes(b"RIFF")
        (tmp_path / "notes.txt").write_text("skip me")

        await digitakt.call("upload_samples", local_path=str(tmp_path), drive_folder="/cipher")

        uploads = [c for c in cli.calls if c[0] == "elektron:sample:ul"]
        assert [(Path(c[1]).name, c[2]) for c in uploads] == [("drum loop 2bar 89bpm.wav", "1:/cipher/Atoll")]


class TestMissingElektroid:
    async def test_tools_say_how_to_install_it(self, digitakt, monkeypatch):
        monkeypatch.setattr(elektroid.shutil, "which", lambda name: None)

        with pytest.raises(ToolError, match="Install Elektroid"):
            await digitakt.call("list_drive")
