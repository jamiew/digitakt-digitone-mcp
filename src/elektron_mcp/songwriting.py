"""Resource-backed songwriting guidance and workflow prompts.

Keep this knowledge out of tool descriptions: it is useful context, not a MIDI command,
and resources do not spend the device tool-schema budget.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Annotated, Any

from pydantic import Field

GUIDE = files("elektron_mcp").joinpath("songwriting_guide.md").read_text(encoding="utf-8")
TECHNIQUES = files("elektron_mcp").joinpath("songwriting_techniques.md").read_text(encoding="utf-8")
EXPERT_VOICES = files("elektron_mcp").joinpath("songwriting_expert_voices.md").read_text(encoding="utf-8")
SYSTEM = "\n\n".join((GUIDE, TECHNIQUES, EXPERT_VOICES))


def register(mcp: Any) -> None:
    """Register shared composition resources and prompts on a device server."""

    @mcp.resource("songwriting://guide", mime_type="text/markdown")
    def songwriting_guide() -> str:
        """General and genre-specific songwriting, groove, and arrangement guidance."""
        return GUIDE

    @mcp.resource("songwriting://techniques", mime_type="text/markdown")
    def songwriting_techniques() -> str:
        """Practical fills, transitions, energy moves, harmony, and originality techniques."""
        return TECHNIQUES

    @mcp.resource("songwriting://expert-voices", mime_type="text/markdown")
    def songwriting_expert_voices() -> str:
        """Cited and conflicting practitioner perspectives translated into listening tests."""
        return EXPERT_VOICES

    @mcp.prompt(title="Arrange a song")
    def arrange_song(
        genre: Annotated[
            str,
            Field(
                description=(
                    "Style lens, such as pop, indie rock, hip-hop, house, techno, disco, "
                    "emotive diary-house, UK 140, or drum & bass."
                )
            ),
        ] = "",
        goal: Annotated[str, Field(description="Desired musical result, section, or problem to solve.")] = "",
    ) -> str:
        """Analyze material, propose a reversible structure, and audition transitions."""
        lens = genre or "the song's existing style"
        target = goal or "turn the strongest material into a complete arrangement"
        return (
            f"Read songwriting://guide and songwriting://techniques, then work through this goal: {target}. Use "
            f"{lens} as a lens, not a rulebook. Inspect the actual patterns and routing before prescribing changes. "
            "Name the identity, roles, phrase lengths, groove anchors, section functions, energy arc, and exact "
            "transition points. Propose a reversible pattern and song-row map before changing hardware. Include one "
            "intentional rule-breaking option with its cost, replacement cue, and listening test. Preserve a raw "
            "source pattern, audition each transition in context, and report what changed and why."
        )

    @mcp.prompt(title="Diagnose a groove")
    def diagnose_groove(
        problem: Annotated[str, Field(description="What feels wrong, such as stiff hats or a syncopated kick.")],
        genre: Annotated[str, Field(description="Genre lens for the diagnosis.")] = "",
    ) -> str:
        """Find the smallest rhythm, velocity, or timing change that improves the pocket."""
        lens = f" through a {genre} lens" if genre else ""
        return (
            f"Use songwriting://guide and songwriting://techniques to diagnose this groove{lens}: {problem}. Separate "
            "anchors from syncopation, inspect kick/bass alignment, backbeat placement, velocity hierarchy, "
            "microtiming, hat articulation, and phrase-turn fills. Change one variable at a time, compare in context, "
            "and keep the simplest version that improves head-nod without erasing the track's identity."
        )

    @mcp.prompt(title="Develop a song")
    def develop_song(
        seed: Annotated[str, Field(description="Starting hook, riff, groove, sample, lyric, or feeling.")],
        style: Annotated[
            str,
            Field(description="Primary style or hybrid, including which genre supplies structure and groove."),
        ] = "",
        goal: Annotated[str, Field(description="What the finished song should make the listener feel or do.")] = "",
    ) -> str:
        """Turn a musical seed into a concrete writing, beat-making, and arrangement plan."""
        lens = style or "the seed's natural style"
        promise = goal or "make the seed into a finished song without losing its identity"
        return (
            f"Read songwriting://guide, songwriting://techniques, and songwriting://expert-voices. Develop this seed: "
            f"{seed}. The goal is to {promise}, using {lens}. Write a one-sentence brief, name the identity and hook, "
            "assign musical roles, and propose the smallest complete cell. Give a section-function map with exact bar "
            "ranges, applied melody/harmony/rhythm choices, and a pattern-machine translation. For a hybrid, name the "
            "structural home, groove home, emotional home, and borrowed vocabulary. Offer at most three meaningfully "
            "different options with tradeoffs. Contrast two relevant expert lenses when they lead to different moves, "
            "then include one rule to keep, one rule to test breaking, its replacement cue, and the next listening "
            "experiment."
        )

    @mcp.prompt(title="Study a reference song")
    def study_reference(
        cipher_folder: Annotated[
            str,
            Field(description="Cipher analysis folder, e.g. ~/dev/cipher/analysis/<song>."),
        ],
        question: Annotated[
            str,
            Field(description="One structural question to answer, such as how the second drop changes."),
        ] = "",
    ) -> str:
        """Compare Cipher evidence, listening, and public form guidance without treating labels as truth."""
        focus = question or "how identity, section function, and energy develop across the song"
        return (
            f"Read the 'Studying reference songs with Cipher' section of songwriting://guide. Study {cipher_folder} "
            f"to answer: {focus}. Inspect analysis.json, beats, ws_cache.json, chords, lyrics, stems, and MIDI where "
            "available. Normalize half/double tempo before converting time to bars. Treat Cipher's A-H boundaries "
            "and chord labels as hypotheses, then rename sections by audible function. Compare the result with the "
            "relevant genre default. Report observations separately from inferences, identify conventions kept or "
            "broken and what replaces their job, and extract relationships rather than copyrighted melody or lyrics."
        )

    @mcp.prompt(title="Break a songwriting rule")
    def break_songwriting_rule(
        convention: Annotated[str, Field(description="Convention to challenge, such as an eight-bar phrase.")],
        purpose: Annotated[str, Field(description="Desired emotional, rhythmic, narrative, or functional effect.")],
        style: Annotated[str, Field(description="Genre or hybrid context.")] = "",
    ) -> str:
        """Design an intentional rule break with a replacement cue and comparison test."""
        lens = f" in {style}" if style else ""
        return (
            "Read songwriting://guide, songwriting://techniques, and songwriting://expert-voices. Challenge this "
            f"convention{lens}: {convention}. The intended effect is: {purpose}. State the convention's normal job, "
            "the exact violation, its listener cost, and the cue that will replace the lost function. Give a control "
            "version and one committed rule-breaking version using exact bars, beats, notes, roles, or automation. "
            "Name one practitioner lens that supports the experiment and one that creates a useful objection. Define "
            "the shortest A/B listening test that can decide whether the break serves the song."
        )

    @mcp.prompt(title="Design a songwriting move")
    def design_songwriting_move(
        problem: Annotated[str, Field(description="The section or writing problem to solve.")],
        effect: Annotated[str, Field(description="What the listener should feel, notice, or do next.")],
        style: Annotated[str, Field(description="Genre, hybrid, or performance context.")] = "",
    ) -> str:
        """Choose and test a concrete fill, transition, switchup, or harmonic move."""
        lens = f" in {style}" if style else ""
        return (
            "Read songwriting://guide, songwriting://techniques, and songwriting://expert-voices. Design a move"
            f"{lens} for this problem: {problem}. The intended listener effect is: {effect}. Diagnose which energy, "
            "narrative, groove, or harmonic job is missing. Give a conservative control and two materially different "
            "moves with exact bars, beats, roles, notes, scale degrees, or automation targets. For each, name its cost "
            "and a relevant practitioner lens. Prefer material derived from the song over stock effects. End with the "
            "smallest level-matched, in-context listening test that can choose among them."
        )
