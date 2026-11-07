"""CLI: `uv run python -m harness <digitakt|digitone> [chat|test|call|smoke] ...`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from typing import Any

from dotenv import load_dotenv

from harness.providers import PROVIDERS, ToolCall, make_provider, pick_provider
from harness.scenarios import SCENARIOS
from harness.session import REPO, Session, connect, describe, paint, parse_value, run_prompt


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness",
        description="Drive the Elektron MCP servers with a real LLM, or call tools directly.",
    )
    p.add_argument("device", choices=sorted(SCENARIOS), help="which server from .mcp.json to launch")
    p.add_argument("--dry-run", action="store_true", help="run the server in-process and capture MIDI, no hardware")
    p.add_argument("--provider", choices=sorted(PROVIDERS), help="default: the first one with an API key set")
    p.add_argument("--model", help="override the provider's default model")
    commands = p.add_subparsers(dest="command")

    commands.add_parser("chat", help="talk to the device (the default)")

    test = commands.add_parser("test", help="run the scenario suite; exits non-zero on failure")
    test.add_argument("-k", dest="only", help="only run scenarios whose name contains this")

    call = commands.add_parser("call", help="call one tool directly, no LLM; no tool lists them all")
    call.add_argument("tool", nargs="?")
    call.add_argument("args", nargs="*", metavar="key=value", help="values are parsed as JSON when possible")

    commands.add_parser("smoke", help="play a fixed Digitakt checklist through the tools, no LLM; listen to each")
    return p


async def chat(session: Session, args: argparse.Namespace) -> None:
    name = args.provider
    provider = make_provider(name, args.model, session.system_prompt, session.tools)
    print(paint(f"{session.device} via {provider.label}. /reset starts over, Ctrl-D quits.", "2"))

    while True:
        try:
            prompt = (await asyncio.to_thread(input, "you> ")).strip()
        except EOFError:
            print()
            return
        if not prompt:
            continue
        if prompt == "/reset":
            provider = make_provider(name, args.model, session.system_prompt, session.tools)
            print(paint("(new conversation)", "2"))
            continue
        answer, _ = await run_prompt(session, provider, prompt)
        print(answer.strip())


async def test(session: Session, args: argparse.Namespace) -> int:
    name = args.provider
    scenarios = [s for s in SCENARIOS[session.device] if not args.only or args.only in s.name]
    if session.dry_run:
        skipped = [s.name for s in scenarios if s.hardware_only]
        scenarios = [s for s in scenarios if not s.hardware_only]
        if skipped:
            print(paint(f"(dry run: skipping {', '.join(skipped)}, which need the device's storage)", "2"))
    failed = 0

    for scenario in scenarios:
        # A fresh conversation per scenario, so one can't lean on another's context.
        provider = make_provider(name, args.model, session.system_prompt, session.tools)
        print(paint(f"\n{scenario.name}: {scenario.prompt}", "1"))
        started = time.monotonic()
        answer, outcomes = await run_prompt(session, provider, scenario.prompt)
        missing = scenario.failures(outcomes)
        elapsed = time.monotonic() - started

        if answer:
            print(paint(f"  “{answer.strip()}”", "2"))
        if missing:
            failed += 1
            print(paint(f"  FAIL after {len(outcomes)} calls, {elapsed:.1f}s. Never saw: {'; '.join(missing)}", "31"))
        else:
            print(paint(f"  PASS {len(outcomes)} calls, {elapsed:.1f}s", "32"))

    summary = (
        f"\n{len(scenarios) - failed}/{len(scenarios)} passed on {session.device} with {provider_label(name, args)}"
    )
    print(paint(summary, "31" if failed else "32"))
    return 1 if failed else 0


def provider_label(name: str, args: argparse.Namespace) -> str:
    return f"{name}/{args.model or PROVIDERS[name][1]}"


async def call(session: Session, args: argparse.Namespace) -> int:
    if not args.tool:
        for tool in session.tools:
            summary = (tool.description or "").splitlines()[0]
            print(f"{tool.name:40} {summary}")
        resources = (await session.client.list_resources()).resources
        print("\nresources: " + ", ".join(r.uri for r in resources))
        return 0

    arguments = {}
    for pair in args.args:
        key, sep, raw = pair.partition("=")
        if not sep:
            raise SystemExit(f"Expected key=value, got {pair!r}")
        arguments[key] = parse_value(raw)

    tool_call = ToolCall(id="cli", name=args.tool, arguments=arguments)
    print(paint(f"→ {describe(tool_call)}", "36"))
    outcome = await session.call(tool_call)
    print(paint(outcome.text, "31") if outcome.is_error else outcome.text)
    return 1 if outcome.is_error else 0


_MELODY = [60, 62, 64, 65, 67, 65, 64, 60]
_SCALE = [60, 62, 64, 65, 67, 69, 71, 72, 71, 69, 67, 65, 64, 62, 60, 60]
_DELAYED = [60, 64, 67, 64] * 2 + [62, 65, 69, 65] * 2 + [64, 67, 71, 67] * 2 + [65, 69, 72, 69, 60, 64, 67, 72]

SMOKE: list[tuple[str, str, dict[str, Any], float]] = [
    # (what to listen for, tool, arguments, seconds to wait afterwards)
    ("a note on track 1, then four quick ones", "send_note", {"note": 60, "duration": 0.1}, 0),
    ("", "send_note_sequence", {"notes": [[60, 100, 0.05]] * 4, "delay": 0.2}, 1),
    ("tracks 1-8 in turn", "send_note_sequence", {"notes": [[n, 100, 0.05] for n in range(8)], "delay": 0.3}, 1),
    ("the sequencer starting", "send_midi_start", {}, 3),
    ("it stopping", "send_midi_stop", {}, 2),
    ("the playhead jumping forward two bars", "send_song_position", {"position": 32}, 1),
    ("it resuming from there", "send_midi_continue", {}, 3),
    ("it stopping again", "send_midi_stop", {}, 1),
    ("the playhead returning to the start", "send_song_position", {"position": 0}, 1),
    (
        "2 bars of kicks on track 1",
        "play_pattern_with_tracks",
        {"triggers": [[b, 1, 100] for b in range(8)], "bars": 2},
        1,
    ),
    (
        "a 2-bar melody on the active track",
        "play_pattern_with_melody",
        {"notes": [[b, n, 100, 0.4 if b == 7 else 0.2] for b, n in enumerate(_MELODY)], "bars": 2},
        1,
    ),
    (
        "a 1-bar loop on track 3, four times",
        "play_pattern_with_loop",
        {"loop_notes": [[b / 2, 2, 60 if b % 2 else 80] for b in range(8)], "bars": 4},
        1,
    ),
    (
        "a 1-bar count-in on note 14, then a scale",
        "play_pattern_with_tracks_and_melody",
        {
            "track_triggers": [[b, 1, 100, 14] for b in range(4)],
            "melody_notes": [[4 + b, n, 80 if b % 2 else 85, 0.8 if b == 15 else 0.4] for b, n in enumerate(_SCALE)],
            "bars": 5,
        },
        1,
    ),
    (
        "a 4-bar count-in with no Start, then the sequencer starting at bar 5 under the melody",
        "play_pattern_with_tracks_and_melody",
        {
            "track_triggers": [[b, 1, 100, 14] for b in range(16)],
            "melody_notes": [[16 + b, n, 85, 0.4] for b, n in enumerate(_DELAYED)],
            "bars": 12,
            "midi_start_at_beat": 16,
        },
        0,
    ),
]
"""What the old scripts/hardware/ scripts sent by hand, now through the server's own tools.

Needs samples on tracks 1-8, a melodic sound on the active track, and transport and
clock receive turned on.
"""


async def smoke(session: Session) -> int:
    failed = 0
    for listen, tool, arguments, pause in SMOKE:
        if listen:
            print(paint(f"\nListen for {listen}.", "1"))
        tool_call = ToolCall(id="smoke", name=tool, arguments=arguments)
        print(paint(f"→ {describe(tool_call)}", "36"))
        outcome = await session.call(tool_call)
        print(paint(outcome.text, "31") if outcome.is_error else outcome.text)
        failed += outcome.is_error
        if not session.dry_run:
            await asyncio.sleep(pause)
    print(paint(f"\n{len(SMOKE) - failed}/{len(SMOKE)} calls succeeded", "31" if failed else "32"))
    return 1 if failed else 0


async def main() -> int:
    args = parser().parse_args()
    load_dotenv(REPO / ".env")
    # The in-process server (--dry-run) turns on INFO logging; HTTP request lines are noise.
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    if args.command == "smoke" and args.device != "digitakt":
        raise SystemExit("smoke is a Digitakt checklist")
    if args.command not in ("call", "smoke"):
        args.provider = pick_provider(args.provider)  # before launching anything, so a missing key fails fast

    async with connect(args.device, dry_run=args.dry_run) as session:
        if args.command == "test":
            return await test(session, args)
        if args.command == "call":
            return await call(session, args)
        if args.command == "smoke":
            return await smoke(session)
        await chat(session, args)
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        # asyncio.run has already cancelled the call, which sends MIDI Stop.
        raise SystemExit(130) from None
