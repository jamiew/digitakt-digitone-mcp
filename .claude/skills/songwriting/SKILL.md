---
name: songwriting
description: Use when analyzing or changing composition, groove, arrangement, pattern variation, transitions, song form, or genre conventions on the Digitakt or Digitone.
---

# Songwriting and arrangement

Read `songwriting://guide` when the MCP server is available. Read only the genre references needed for the request.

## Workflow

1. Inspect the actual patterns, sounds, routing, tempo, conditions, and automation before advising.
2. Preserve a raw source pattern before changing hardware.
3. Name the song identity and each track's role: foundation, harmony, foreground, response, or texture.
4. Diagram pattern, pass, phrase, section, and song separately. Do not call a 64-step pattern an eight-bar phrase unless it plays twice.
5. Plan a reversible pattern bank and exact transition points before writing.
6. Prefer subtraction and turn-taking. One busy foreground voice at a time.
7. Use conditionals for local variation. Use another pattern or Song Mode row for exact one-time structural events.
8. Bound automation with explicit start and reset values. Never leave filter, volume, resonance, or envelope state ambiguous.
9. Audition the bar before and after every transition. Read the hardware state back after writing.
10. Explain the musical reason, the exact sequencer mechanism, and how to undo it.

## Reference files

- `references/general.md`: phrase hierarchy, role assignment, density, call and response, transitions.
- `references/hip-hop.md`: loop identity, rapper space, boom-bap groove, subtractive sections.
- `references/pop.md`: hook hierarchy, prosody, section contrast, simple-and-interesting design.
- `references/disco-funk.md`: interlocking rhythm section, space, breakdown and rebuild.
- `references/techno-house.md`: energy curves, phrase-scale automation, builds, breakdowns, drops.
- `references/rock.md`: riff/vocal identity, band roles, dynamics, articulation, fills.
- `references/sources.md`: evidence and creator perspectives. Treat named artists as analytical lenses, not cloning targets.

## Hardware rules

Follow `elektron-bridge` for device safety and persistence. Pattern writes change the live project but do not guarantee a saved project. Remind the user to save on the machine. Direct Digitone CC control through Digitakt MIDI tracks requires verified channel and CC Select mappings; unknown p-lock encoding is not permission to guess.