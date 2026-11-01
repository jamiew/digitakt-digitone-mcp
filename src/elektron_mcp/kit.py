"""Guess a sample's drum role from its name, and pick a kit from the project's slots."""

from __future__ import annotations

import random
import re
from collections.abc import Iterable, Mapping

from elektron_mcp.elektroid import Slot

# Checked in order, so "Kick & Hat" is a kick and "Open Hat" isn't a closed hat.
ROLE_PATTERNS: dict[str, re.Pattern[str]] = {
    "break": re.compile(r"break|\bbeat\b|drum loop|amen|\bbrk\b"),
    "kick": re.compile(r"kick|\bbd\b|bass ?drum"),
    "snare": re.compile(r"snare|\bsd\b|\bsnr\b"),
    "clap": re.compile(r"clap|\bcp\b"),
    "open hat": re.compile(r"open|\boh\b|\bohh\b"),
    "closed hat": re.compile(r"hat|\bhh\b|\bch\b|\bchh\b|closed"),
    "crash": re.compile(r"crash|cymbal|\bcy\b|\bcym\b|ride"),
    "tom": re.compile(r"\btoms?\b|\b[lmh]t\b"),
    "cowbell": re.compile(r"cowbell|\bcb\b"),
}
ROLES = tuple(ROLE_PATTERNS)

DEFAULT_KIT: dict[int, str] = {1: "kick", 2: "snare", 3: "break", 6: "closed hat", 7: "open hat", 8: "crash"}
"""Track -> role. Tracks 4 and 5 (clap, cowbell in the default layout) are left alone."""


def _words(text: str) -> str:
    return re.sub(r"[_\-./()&]+", " ", text.lower())


def role_of(path: str) -> str | None:
    """The role a sample name suggests, falling back to its folder ("Kick/Kick 05")."""
    parts = path.rstrip("/").split("/")
    for part in (parts[-1], parts[-2] if len(parts) > 1 else ""):
        words = _words(part)
        for role, pattern in ROLE_PATTERNS.items():
            if pattern.search(words):
                return role
    return None


def candidates(slots: Iterable[Slot]) -> dict[str, list[Slot]]:
    by_role: dict[str, list[Slot]] = {role: [] for role in ROLES}
    for slot in slots:
        if slot.path and (role := role_of(slot.path)):
            by_role[role].append(slot)
    return by_role


def pick_kit(slots: Iterable[Slot], roles: Mapping[int, str], rng: random.Random) -> dict[int, Slot | None]:
    """One slot per track. Prefers slots no pattern uses yet, so a new kit sounds new."""
    by_role = candidates(slots)
    picks: dict[int, Slot | None] = {}
    for track, role in roles.items():
        pool = by_role[role]
        fresh = [s for s in pool if not s.used]
        picks[track] = rng.choice(fresh or pool) if pool else None
    return picks
