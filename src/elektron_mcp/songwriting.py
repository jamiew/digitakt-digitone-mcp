"""Resource-backed songwriting guidance and workflow prompts.

Keep this knowledge out of tool descriptions: it is useful context, not a MIDI command,
and resources do not spend the device tool-schema budget.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

GUIDE = """# Songwriting and arrangement guide

Use genre as a lens, not a rulebook. Preserve the song's identity, then change one structural variable at a time so the result remains explainable and reversible.

## Shared workflow

1. **Name the identity.** Pick the groove, hook, riff, sample, or progression that must survive every section.
2. **Assign roles.** Foundation, harmony, foreground voice, response, and texture. Let one foreground voice be busy at a time.
3. **Write a phrase before a song.** A pattern is machine memory; a phrase is a musical thought; a section gives that thought a function. Four-, eight-, and sixteen-bar phrases are common, not mandatory.
4. **Make contrast subtractively.** Start from the fullest useful cell. Remove parts to create verses, intros, and breakdowns before adding new material.
5. **Mark boundaries with two signals.** Combine a fill, mute, register change, density change, harmonic turn, or automation gesture. One signal can sound accidental.
6. **Reset automation.** Every temporary filter, resonance, volume, envelope, or send move needs an explicit return value.
7. **Audition in context.** Hear at least one phrase before and after every transition. Judge the landing, not the fill by itself.

## Groove checks

- **Anchor:** Can the kick, snare, bass, and pulse explain the groove alone?
- **Pocket:** Do velocity and microtiming create a hierarchy, or is every hit equally important?
- **Space:** Does each syncopation answer an anchor? Too many displaced accents erase the reference beat.
- **Conversation:** When the lead moves, can the bass hold or rest? When the bass runs, can the lead leave?
- **Turn:** Does the final bar increase activity, remove weight, or redirect pitch toward the next downbeat?

## Genre lenses

### Hip-hop

Treat the rapper as the lead even when no vocal is recorded. Keep one unmistakable loop, chop, riff, or scratch identity; build sections by muting, filtering, changing drum weight, or replacing the foreground response. Favor strong backbeat landmarks and deliberate kick variation over constant syncopation. Use fills at phrase turns, not every bar. A useful eight-bar cell is `A A A A'`, where `A'` changes one or two events.

**Reference lenses:** DJ Premier suggests auditioning through a DJ's ear: does this sound fit this voice, and does the hook remain recognizable? NPR's producer series shows sampling as composition through selection, transformation, and context rather than mere repetition.

### Pop

Make sections easy to identify. Change melodic rhythm, register, density, or instrumentation when the function changes. Keep the harmonic loop simple if the melody supplies contrast. Test the title or central hook against every section: the chorus should frame it more strongly than the verse. Prosody means groove, melody, harmony, texture, and words should reinforce the same emotional direction.

### Disco and funk

Build a strong kick-and-bass foundation, then interlock short parts around it. Economy wins: a few important parts with clear accents beat many continuous layers. Use breakdowns to expose the construction, then rebuild it. Preserve human velocity, articulation, and timing differences; technology serves the groove.

### Techno and house

Think in energy curves and phrase-scale change. Establish a stable pulse, then move one dimension at a time: density, brightness, register, space, or rhythmic subdivision. Builds shorten event spacing or raise spectral energy; breakdowns remove anchors; drops restore the foundation with a clear new fact. Keep long automation bounded by explicit start and reset values.

### Rock

Protect the riff or vocal identity. Arrange the band as changing combinations of rhythm section, harmonic support, riff, lead, and texture. Section contrast usually needs performance contrast: articulation, register, dynamics, cymbal state, guitar width, or vocal layering. Let fills announce boundaries, but make the next downbeat carry the payoff.

## Pattern-machine translation

- **Pattern:** stored sequencer state. It may contain one to four bars on a 64-step grid.
- **Pass:** one playback of that pattern.
- **Conditional variation:** an alternate event chosen by probability, FILL, PRE, or an `x:y` cycle condition.
- **Phrase:** a complete musical thought, often two pattern passes when one pattern holds four bars.
- **Section:** several phrases with one job, such as verse, hook, build, breakdown, or drop.
- **Song row:** a scheduled pattern, repeat count or row length, mutes, and optional tempo.

Use conditions for local variation whose timing can drift without changing form. Use a separate pattern or song row when a transition must happen exactly once, when several tracks must change together, or when the row needs a different length.

## Review checklist

A revision is ready to keep when:

- the identity remains audible;
- each section has a named function;
- every busy foreground part has space around it;
- transitions land on the intended downbeat;
- conditional events cannot collide with their fallback events;
- automation returns to a known state;
- the full sequence works without manual rescue.

## Sources

- Ableton, [Arranging as a Subtractive Process](https://makingmusic.ableton.com/arranging-as-a-subtractive-process).
- Open Music Theory, [The Phrase, Archetypes, and Unique Forms](https://pressbooks.nebraska.edu/openmusictheory/chapter/phrase-archetypes-unique-forms/).
- Open Music Theory, [Introduction to Form in Popular Music](https://pressbooks.nebraska.edu/openmusictheory/chapter/intro-to-form-in-popular-music/).
- Berklee, [Jack Perricone on melody, groove, harmony, texture, prosody, and “simple and interesting”](https://www.berklee.edu/berklee-today/summer-2018/Expert-Testimony).
- NPR Music, [Sampling Ain't Dead: Hip-Hop Producers Break Down the Formula](https://www.npr.org/2020/04/30/848488734/sampling-aint-dead-hip-hop-producers-break-down-the-formula).
- Journal on the Art of Record Production, [Nile Rodgers: Navigating Production Space](https://www.arpjournal.com/asarpwp/nile-rodgers-navigating-production-space/).
- NPR Music, [Pharrell Williams on juxtaposition and his writing process](https://www.npr.org/sections/therecord/2013/12/31/258406317/pharrell-williams-on-juxtaposition-and-seeing-sounds).
- Rolling Stone, [DJ Premier on listening as a DJ and matching production to an artist](https://www.rollingstone.com/music/music-features/dj-premier-interview-new-ep-1388437/).
"""


def register(mcp: Any) -> None:
    """Register shared composition resources and prompts on a device server."""

    @mcp.resource("songwriting://guide", mime_type="text/markdown")
    def songwriting_guide() -> str:
        """General and genre-specific songwriting, groove, and arrangement guidance."""
        return GUIDE

    @mcp.prompt(title="Arrange a song")
    def arrange_song(
        genre: Annotated[str, Field(description="Genre lens, such as hip-hop, pop, disco, techno, or rock.")] = "",
        goal: Annotated[str, Field(description="Desired musical result, section, or problem to solve.")] = "",
    ) -> str:
        """Analyze material, propose a reversible structure, and audition transitions."""
        lens = genre or "the song's existing style"
        target = goal or "turn the strongest material into a complete arrangement"
        return (
            f"Use the songwriting://guide resource and work through {target} using {lens} as a lens. "
            "First inspect or ask for the actual patterns and routing. Name the song identity, track roles, "
            "phrase lengths, density, groove anchors, and exact transition points. Propose a pattern and song-row "
            "map before changing hardware. Preserve a raw source pattern, keep changes reversible, audition each "
            "transition in context, and report what changed and why."
        )

    @mcp.prompt(title="Diagnose a groove")
    def diagnose_groove(
        problem: Annotated[str, Field(description="What feels wrong, such as stiff hats or a syncopated kick.")],
        genre: Annotated[str, Field(description="Genre lens for the diagnosis.")] = "",
    ) -> str:
        """Find the smallest rhythm, velocity, or timing change that improves the pocket."""
        lens = f" through a {genre} lens" if genre else ""
        return (
            f"Use the songwriting://guide resource to diagnose this groove{lens}: {problem}. Separate anchors from "
            "syncopation, inspect kick/bass alignment, backbeat placement, velocity hierarchy, microtiming, hat "
            "articulation, and phrase-turn fills. Change one variable at a time, compare in context, and keep the "
            "simplest version that improves head-nod without erasing the track's identity."
        )
