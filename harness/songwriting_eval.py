"""Live LLM evaluation for the songwriting guide.

Run with `uv run python -m harness.songwriting_eval`. Each case asks one model to
apply the guide and a fresh model to judge the answer against case-specific criteria.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from elektron_mcp.songwriting import SYSTEM
from harness.providers import PROVIDERS, Provider, make_provider, pick_provider
from harness.session import REPO, paint


@dataclass(frozen=True)
class Case:
    name: str
    prompt: str
    criteria: tuple[str, ...]


CASES = (
    Case(
        "indie-pop-chorus",
        "I have a four-bar i-♭VI-♭III-♭VII guitar loop at 108 BPM. The verse and chorus feel identical. "
        "Turn it into a 2:40 indie-pop/rock song. Give me one clear chorus and one version where the chorus gets "
        "smaller instead of bigger.",
        (
            "Names the likely identity before prescribing layers.",
            "Gives an exact section and bar plan that plausibly fits about 2:40 at 108 BPM.",
            "Creates verse/chorus contrast on specific musical axes, not only loudness.",
            "Explains the smaller-chorus rule break, its cost, replacement cue, and A/B test.",
        ),
    ),
    Case(
        "hip-hop-vocal-space",
        "My 94 BPM eight-bar sample beat has drums, bass, three chops, a synth lead, and scratches playing almost "
        "constantly. Arrange a 64-bar hip-hop song for a rapper without losing the sample identity.",
        (
            "Treats the unrecorded rapper as the foreground voice and creates specific rhythmic or spectral gaps.",
            "Provides a concrete 64-bar map with hook, verse, phrase turns, and transitions.",
            "Preserves one unmistakable sample identity while reducing competition.",
            "Uses deliberate drum, bass, mute, or filter changes instead of generic calls for variation.",
        ),
    ),
    Case(
        "diary-house-hybrid",
        "Build a song around a vulnerable phone voice memo and two warm piano chords at 123 BPM. Make the memo shape "
        "speech rhythm and harmonic timing, include a concrete source-consent check, and create Fred-again-adjacent "
        "emotional intimacy, house movement, and an indie-pop arc without copying a specific record.",
        (
            "Names structural, groove, emotional, and borrowed-vocabulary homes for the hybrid.",
            "Makes the voice memo drive cadence, harmony, and narrative rather than serving as decoration.",
            "Gives a concrete private-to-communal arrangement and explains each payoff.",
            "Addresses source context or consent and avoids prescribing a direct artist imitation.",
        ),
    ),
    Case(
        "bass-music-weave",
        "I have a 140 BPM half-time sub riff and a chopped break that also works at 175 BPM. Design a track that moves "
        "from spacious UK 140 into drum & bass without sounding like two songs pasted together.",
        (
            "Chooses a coherent counting or transition strategy instead of treating 140 and 175 as interchangeable.",
            "Uses a shared motif, tonal center, sample, or transition cue as glue.",
            "Gives exact phrase lengths and assigns clear sub, mid-bass, break, and foreground roles.",
            "Names the continuity cost of the genre shift and a listening test for whether it works.",
        ),
    ),
    Case(
        "cipher-skepticism",
        "Cipher analyzed a drum & bass reference as 112.3 BPM and split it into eight chroma sections of about 5, "
        "16, 5, 16, 6, 8, 5, and 33 bars. What can I safely learn from this about structure?",
        (
            "Separates machine observations from musical inferences.",
            "Flags tempo-grid ambiguity and validates against snare, beat, lyrics, or phrase boundaries.",
            "Explains that fixed A-H chroma segments are chronological candidates, not semantic form labels.",
            "Extracts useful hypotheses without claiming to have heard the track or inventing verse/drop names.",
        ),
    ),
    Case(
        "seven-bar-prechorus",
        "My pop pre-chorus naturally resolves after seven bars. Should I force it to eight? Show the normal and broken-"
        "rule versions and tell me how to decide.",
        (
            "Explains the predictive job of an eight-bar phrase without treating it as mandatory.",
            "Provides exact seven- and eight-bar alternatives.",
            "Names the cost of seven bars and a pickup, pedal, lyric, backbeat, or other replacement cue.",
            "Ends with a short in-context A/B test rather than a verdict based on theory alone.",
        ),
    ),
    Case(
        "transition-toolkit",
        "I have a 16-bar house buildup into a drop at 126 BPM. The stock riser and snare roll work, but they make the "
        "song sound generic. Give me three materially different transitions built from my vocal hook and drum groove.",
        (
            "Diagnoses the transition's job and names the energy axes each option changes.",
            "Gives three exact, materially different approaches, including a material-derived or negative-space move.",
            "Specifies bar- or beat-level execution and protects kick/bass impact at the landing.",
            "Names each option's cost and ends with a level-matched in-context test.",
        ),
    ),
    Case(
        "originality-conflict",
        "My indie-dance demos sound like a collage of my favorite artists. Give me a four-week plan to find a more "
        "personal combination without pretending influence can disappear.",
        (
            "Uses at least two specifically named, meaningfully conflicting practitioner lenses.",
            "Turns personal sources, constraints, combinations, or performance traits into concrete weekly work.",
            "Avoids vague advice to be authentic and avoids tracing one artist's whole style stack.",
            "Defines a body of work and comparison method that can reveal recurring personal choices.",
        ),
    ),
    Case(
        "parallel-mode-bridge",
        "My chorus is C major: C-G-Am-F. Design an eight-bar bridge that moves into C minor, then returns to the same "
        "chorus melody. Give me smooth and abrupt versions with exact chords, bass, and melody notes, plus a no-mode-"
        "change control for comparison.",
        (
            "Correctly distinguishes isolated modal mixture from a sustained parallel-minor shift with C still tonic.",
            "Gives exact eight-bar smooth and abrupt alternatives with bass and melody treatment.",
            "Uses a common tone, voice leading, direct cut, or another named mechanism accurately.",
            "Explains the emotional cost and provides the requested no-mode-change control.",
        ),
    ),
    Case(
        "hypnotic-techno",
        "My 32-bar techno loop gets boring, but changing clips every eight bars kills the trance. Show how to arrange "
        "three minutes around one invariant and slow continuous changes. Address the advice that every second must be "
        "awesome.",
        (
            "Names one invariant and schedules exact continuous and discrete processes over a plausible form.",
            "Uses automation for orientation or disorientation rather than generic constant motion.",
            "Contrasts Max Martin's attention lens with a repetition- or material-led lens without caricaturing either.",
            "Ends with a test for hypnotic engagement that does not require novelty every eight bars.",
        ),
    ),
)

SUBJECT_SYSTEM = f"""You are a practical songwriting and beat-making coach. Use the three resources below as your
operating system. Diagnose before prescribing. Give exact bars, beats, roles, notes, scale degrees, mutes, or automation
where useful. Explain why each choice works. Treat genre conventions and expert advice as testable lenses, not laws.
When an expert lens materially changes the plan, name the practitioner and the relevant source idea; do not use
authority as proof. Include intentional rule-breaking only with its cost, replacement cue, and test. Never claim to
hear audio you were not given. Keep the answer under 700 words.

{SYSTEM}
"""

JUDGE_SYSTEM = """You evaluate songwriting advice. Return one JSON object and nothing else:
{"pass": true, "score": 1, "reason": "short explanation", "missed": ["criterion"]}

Score from 1 to 5. Pass only when every case criterion is materially satisfied, the advice is concrete and internally
consistent, theory is explained as cause rather than law, and the answer never claims to hear unavailable audio.
Do not reward length, confident tone, or copying criterion words without an actionable musical plan.
"""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Evaluate the songwriting guide with live writer and judge calls.")
    result.add_argument("-k", dest="only", help="only run cases whose name contains this")
    result.add_argument("--provider", choices=sorted(PROVIDERS), help="writer provider")
    result.add_argument("--model", help="writer model override")
    result.add_argument("--judge-provider", choices=sorted(PROVIDERS), help="default: writer provider")
    result.add_argument("--judge-model", help="judge model override")
    return result


async def complete_once(provider: Provider, prompt: str) -> str:
    provider.add_user(prompt)
    reply = await provider.complete()
    if reply.tool_calls:
        raise RuntimeError("The songwriting evaluator does not expose tools.")
    return reply.text.strip()


def parse_judgment(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"Judge returned no JSON object: {text}")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict) or not isinstance(value.get("pass"), bool):
        raise ValueError(f"Judge returned an invalid result: {text}")
    return value


def judge_prompt(case: Case, answer: str) -> str:
    criteria = "\n".join(f"- {criterion}" for criterion in case.criteria)
    return f"""User prompt:
{case.prompt}

Required criteria:
{criteria}

Candidate answer:
{answer}
"""


async def run(args: argparse.Namespace) -> int:
    writer_name = pick_provider(args.provider)
    judge_name = pick_provider(args.judge_provider or writer_name)
    cases = [case for case in CASES if not args.only or args.only in case.name]
    if not cases:
        raise SystemExit(f"No songwriting eval case matches {args.only!r}.")

    failed = 0
    for case in cases:
        print(paint(f"\n{case.name}: {case.prompt}", "1"))
        started = time.monotonic()
        writer = make_provider(writer_name, args.model, SUBJECT_SYSTEM, [])
        answer = await complete_once(writer, case.prompt)
        print(answer)

        judge = make_provider(judge_name, args.judge_model, JUDGE_SYSTEM, [])
        judgment = parse_judgment(await complete_once(judge, judge_prompt(case, answer)))
        elapsed = time.monotonic() - started
        passed = judgment["pass"]
        failed += not passed
        missed = judgment.get("missed") or []
        detail = f"; missed: {'; '.join(str(item) for item in missed)}" if missed else ""
        verdict = f"{'PASS' if passed else 'FAIL'} {judgment.get('score', '?')}/5 in {elapsed:.1f}s: {judgment.get('reason', '')}{detail}"
        print(paint(verdict, "32" if passed else "31"))

    label = f"{len(cases) - failed}/{len(cases)} passed with {writer_name}/{args.model or PROVIDERS[writer_name][1]}"
    print(paint(f"\n{label}", "32" if not failed else "31"))
    return 1 if failed else 0


async def main() -> int:
    args = parser().parse_args()
    load_dotenv(REPO / ".env")
    return await run(args)


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
