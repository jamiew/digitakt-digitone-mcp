---
name: elektron-bridge
description: Use when working with the Digitakt or Digitone through this repo's MCP servers — playing and shaping sounds, seeing what's on the +Drive or in the project's sample slots, loading samples onto tracks, bootstrapping a kit (kick/snare/hats/crash/break, or Digitone pad/keys/bass/lead), or moving Cipher sample packs onto the device.
---

# Elektron bridge: MCP + elektroid

Two tools share the one USB cable. Use each for what it's good at.

| Job | Use | Notes |
|---|---|---|
| Notes, patterns, clock, CC/NRPN, sequencer trigs | MCP (`digitakt` / `digitone` servers) | plain MIDI |
| Switch a Digitakt track to another sample **already in the project** | MCP `set_parameter(name="sample_slot", value=N, channel=T)` | verified: value N = RAM slot N |
| List the +Drive, the project's 127 sample slots, which slot each track uses | `elektroid-cli` | read-only, safe |
| Upload a WAV, or put a new sample on a track | `elektroid-cli` | writes to the device: ask first |
| Digitone sounds, both machines' projects | `elektroid-cli` (`sound`, `project`, `data`) | Digitone has no samples at all |

The MCP servers can't see storage yet. Until they can, run `elektroid-cli` from the shell.

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

1. `ram:ls` the project slots. Bucket them by path keywords: `kick|bd`, `snare|sd|clap`,
   `hat|hh` (closed) vs `oh|open`, `crash|cy|ride`, and `break|loop|beat`.
2. Pick one per role at random from its bucket. Prefer slots not marked `[ used ]` to keep
   it fresh, unless a bucket only has used ones.
3. For each role, call the MCP: `set_parameter(name="sample_slot", value=<slot>, channel=<track>)`.
4. Confirm with `track:ls`, then audition: `trigger_track` for each track, then a 2-bar
   `play_pattern_with_tracks`.
5. When a role has no candidate in the slots, look on the +Drive (`sample:ls` under
   `drums`, `breaks`, `D&P onehits selected/...`) and offer to upload it with `track:ul`.

Report the result as a table of track, role, slot and path, so the user can undo it.

## Recipe: Cipher packs onto the device

`~/dev/cipher` cuts samples from songs. Its Digitakt packs land in
`~/dev/cipher/exports/<pack>/`, one folder per song, as 48 kHz 16-bit mono files that are
normalized and named by role (`drum loop 2bar 89bpm`, `bass loop 1bar 123bpm`). The
+Drive already has a `/cipher/<song date>/` tree from earlier transfers.

1. List the pack folder locally and show the user what's in it.
2. With their OK: `sample:mkdir "1:/cipher/<song>"`, then `sample:ul` each file into it.
3. To audition right away, `track:ul` the chosen files onto tracks instead, then play them.

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
