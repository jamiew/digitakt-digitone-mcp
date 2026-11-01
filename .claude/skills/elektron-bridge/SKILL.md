---
name: elektron-bridge
description: Use when working with the Digitakt or Digitone through this repo's MCP servers — playing and shaping sounds, seeing what's on the +Drive or in the project's sample slots, loading samples onto tracks, bootstrapping a kit (kick/snare/hats/crash/break, or Digitone pad/keys/bass/lead), or moving Cipher sample packs onto the device.
---

# Elektron bridge: MCP + elektroid

The Digitakt MCP server now has storage tools: `list_drive`, `list_sample_slots`,
`load_sample`, `upload_samples`, `bootstrap_kit` and `list_sounds`. They run
`elektroid-cli` under the hood. **Prefer the tools.** Drop to the raw CLI only for
things they don't cover yet (projects, sound files, the Digitone).

| Job | Use | Notes |
|---|---|---|
| Notes, patterns, clock, CC/NRPN, sequencer trigs | MCP | plain MIDI |
| See the +Drive, slots, which slot each track plays | MCP `list_drive`, `list_sample_slots` | read-only, safe |
| Put a sample on a track | MCP `load_sample(track, sample)` | instant for samples already in the project |
| A new random kit | MCP `bootstrap_kit(dry_run=true)`, then without `dry_run` | only switches slots |
| Copy a folder of WAVs onto the +Drive | MCP `upload_samples` | writes to the device: ask first |
| Digitone sounds, projects on either machine | `elektroid-cli` (`sound`, `project`, `data`) | Digitone has no samples at all |

**The AUTO channel catch (seen on hardware):** track sample changes go out as a CC on the
track's channel. On a unit where channel 1 is also the AUTO channel, a change meant for
track 1 lands on whichever track is active. `load_sample` and `bootstrap_kit` read the
tracks back and warn when this happens. Pass the warning on, and suggest giving the AUTO
channel its own number in Settings > MIDI > Channels.

## Setup

- `elektroid-cli` comes from [Elektroid](https://github.com/dagargo/elektroid). On this
  machine it's installed through a local Homebrew tap (`elektroid/local/elektroid`).
- Device numbers depend on what's plugged in. Run `elektroid-cli ld` first and use the
  number shown for "Elektron Digitakt" (it was `1` with a Volca Sample also connected).
- Quote paths: folder names have spaces and `&`.

## Look before touching (read-only)

```bash
elektroid-cli ld                                   # devices
elektroid-cli info 1                               # OS version + filesystems (Digitakt 1.52A: data, project, ram, sample, sound, track, track-loop)
elektroid-cli df 1:/                               # +Drive and RAM usage
elektroid-cli elektron:sample:ls 1:/               # +Drive folders
elektroid-cli elektron:sample:ls "1:/D&P onehits selected/Kick"
elektroid-cli elektron:ram:ls 1:/                  # project slots: "F size N NNN /path [ used ]"
elektroid-cli elektron:track:ls 1:/                # tracks 1-8: "[ slot=16:path=/... ]"
elektroid-cli elektron:project:ls 1:/              # projects on the +Drive
elektroid-cli elektron:data:ls 1:/soundbanks/A     # sound pool names
```

`track:ls` reflects changes immediately, so it's the way to confirm a `sample_slot` change.

## Change things (ask the user first)

- `elektroid-cli elektron:sample:mkdir "1:/cipher/<song>"`
- `elektroid-cli elektron:sample:ul file.wav "1:/cipher/<song>"` uploads to the +Drive.
- `elektroid-cli elektron:ram:ul file.wav 1:/N` loads a **local** WAV into RAM slot N.
- `elektroid-cli elektron:track:ul file.wav 1:/T` loads a local WAV onto track T, using a
  free slot.

Both `ram:ul` and `track:ul` upload a fresh copy into `/incoming` on the +Drive first, even
if the sample already lives elsewhere there. To put an existing +Drive sample on a track
without that duplicate, it has to be in the project's slots already: then use
`sample_slot`. If it isn't, `sample:dl` it and `track:ul` it, and tell the user about the
`/incoming` copy.

Never run `rm`, `rmdir`, `cl`, `mv` or `sw` unless the user names that exact action. The
+Drive holds their whole library. Slot and track changes live in the unsaved project, so
remind them to save the project on the device if they want to keep the result.
(Unverified: whether a project reload discards a `track:ul`.)

## Recipe: bootstrap a Digitakt kit

Goal: kick, snare, closed hat, open hat, crash and a break on tracks, picked semi-randomly.
The creator's layout is 1 kick, 2 snare, 3 tom, 4 clap, 5 cowbell, 6 closed hat, 7 open
hat and 8 cymbal. Ask where the break should go, or use track 3 or 5.

1. `bootstrap_kit(dry_run=true)` and show the picks. It reads the project's slots, guesses
   roles from names (kick, snare, clap, open hat, closed hat, crash, tom, cowbell, break),
   and prefers slots no pattern uses yet. The default is 1 kick, 2 snare, 3 break,
   6 closed hat, 7 open hat and 8 crash. Pass `roles` to change it, and `seed` to repeat a
   pick.
2. If the user likes it, run it again without `dry_run` and the same `seed`.
3. Audition: `trigger_track` for each changed track, then a 2-bar `play_pattern_with_tracks`.
4. For a role with no candidate, `list_drive` under `drums`, `breaks` or
   `D&P onehits selected/...`, then offer `load_sample(track, "/that/path")`. That one
   uploads into a free slot, with a copy in `/incoming`.

Report the result as a table of track, role, slot and the "was slot", so the user can
undo it with `load_sample(track, <old slot>)`.

## Recipe: Cipher packs onto the device

`~/dev/cipher` cuts samples from songs. Its Digitakt packs land in
`~/dev/cipher/exports/<pack>/`, one folder per song, as 48 kHz 16-bit mono files that are
normalized and named by role (`drum loop 2bar 89bpm`, `bass loop 1bar 123bpm`). The
+Drive already has a `/cipher/<song date>/` tree from earlier transfers.

1. List the pack folder locally and show the user what's in it.
2. With their OK: `upload_samples(local_path="<pack>", drive_folder="/cipher")`. It
   keeps one subfolder per song. The `load_cipher_pack` prompt does all of this.
3. To audition, `load_sample(track, "/cipher/<song>/<name>")` for the ones they want,
   then play them. Anything not already in a slot goes into a free one.

Cipher's **Chain** export makes equal-slice sample chains. The original Digitakt has no
slice mode, so play a slice by setting `sample_start` before each hit. With N equal slices,
slice k (0-based) starts at about `round(k * 128 / N)`.

## Recipe: bootstrap a Digitone (texture, keys, bass, lead)

The Digitone is FM only, so "loading" means sounds, not samples. There are two ways in:

- **Build the patch over MIDI (works now).** On tracks 1-4 (channels 1-4). Values are raw
  0-127, not the numbers on the screen, so treat these as starting points and listen:
  - Texture/pad: `set_algorithm` 5 to 8, a slow `amp_attack` (90+), a long `amp_release`
    (100+), some `chorus_send`, and a slow, deep LFO (`lfo1_speed` low, `lfo1_depth` mid).
  - Keys: algorithm 1 or 2, a short `op_a_decay`, a medium `amp_decay`, and ratios that
    sound harmonic, i.e. whole-number ratios on the screen.
  - Bass: algorithm 1, low `fm_ratio_*` values, a high-ish `op_b_level` with a short
    `op_b_decay` for the pluck, `filter_cutoff` around 40-60, and short notes.
  - Lead: algorithm 2 to 4, a bit of `fm_feedback`, a medium `amp_attack`, and `delay_send`.
  Randomize inside those ranges, then play a short phrase on each track to audition it.
- **Pick from the sound pool.** `elektroid-cli elektron:data:ls <dev>:/soundbanks/A`
  (through H) lists sound names you can choose by keyword. There's no known remote command
  to load a pool sound onto a track, so tell the user which sound to load on the device.

The Digitone in the creator's setup sits behind the Digitakt over MIDI DIN, so it isn't
on USB and `elektroid-cli` can't reach it. It's played from Digitakt MIDI tracks on
channels 9-16. To patch it from the `digitone` MCP server, it has to be on USB itself.

## Testing

- `uv run python -m harness digitakt call` lists the MCP tools without an API key.
- `uv run python -m harness digitakt` opens a chat with the device (needs an API key).
- See README "Testing it" for the full ladder.
