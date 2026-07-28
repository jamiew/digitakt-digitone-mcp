"""Device description types.

A device is *data*: a port name, a track count, a parameter table, plus a hook to
register the handful of tools that only make sense for that machine. Everything
else lives in the shared core, so adding a Digitakt II or a Syntakt means writing
one of these, not forking a server.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from elektron_mcp.server import DeviceServer

ParamKind = Literal["cc", "nrpn"]

# Raw parameter tables are written as plain dicts (they're big data files, and
# dicts keep them readable/diffable). Mapping rather than dict because dict is
# invariant, and the tables have concrete value types like str | int | tuple.
RawParameter = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Parameter:
    """A single addressable parameter, typed so callers don't guess at dict keys."""

    name: str
    kind: ParamKind
    minimum: int
    maximum: int
    cc: int | None = None
    msb: int | None = None
    lsb: int | None = None

    def clamp(self, value: int) -> int:
        return max(self.minimum, min(self.maximum, value))

    def in_range(self, value: int) -> bool:
        return self.minimum <= value <= self.maximum


def parse_parameters(raw: Mapping[str, RawParameter]) -> dict[str, Parameter]:
    """Build the typed parameter table from a device's raw dict.

    Raises on malformed entries so a bad table fails at import, not mid-performance.
    """
    parsed: dict[str, Parameter] = {}

    for name, entry in raw.items():
        declared = entry.get("type")
        # Assigned branch-by-branch rather than checked with `in`, so the literal type survives.
        if declared == "cc":
            kind: ParamKind = "cc"
        elif declared == "nrpn":
            kind = "nrpn"
        else:
            raise ValueError(f"parameter {name!r}: type must be 'cc' or 'nrpn', got {declared!r}")

        value_range = entry.get("range")
        if not (isinstance(value_range, tuple) and len(value_range) == 2):
            raise ValueError(f"parameter {name!r}: 'range' must be a (min, max) tuple, got {value_range!r}")
        minimum, maximum = value_range
        if not isinstance(minimum, int) or not isinstance(maximum, int):
            raise ValueError(f"parameter {name!r}: range bounds must be ints, got {value_range!r}")

        cc = entry.get("cc")
        msb = entry.get("msb")
        lsb = entry.get("lsb")

        if kind == "cc" and not isinstance(cc, int):
            raise ValueError(f"parameter {name!r}: cc parameters need an int 'cc', got {cc!r}")
        if kind == "nrpn" and not (isinstance(msb, int) and isinstance(lsb, int)):
            raise ValueError(f"parameter {name!r}: nrpn parameters need int 'msb' and 'lsb', got {msb!r}/{lsb!r}")

        parsed[name] = Parameter(
            name=name,
            kind=kind,
            minimum=minimum,
            maximum=maximum,
            cc=cc if isinstance(cc, int) else None,
            msb=msb if isinstance(msb, int) else None,
            lsb=lsb if isinstance(lsb, int) else None,
        )

    return parsed


@dataclass(frozen=True, slots=True)
class DeviceSpec:
    """Everything the shared server needs to speak to one Elektron machine."""

    # Identity
    slug: str
    """Short id: used for the server name and the ~/.mcp-config/<slug>/ storage dir."""
    display_name: str
    """Human name used in tool output and log lines, e.g. "Digitakt"."""
    port_name: str
    """Substring matched against MIDI port names, e.g. "Elektron Digitakt"."""

    # Layout
    track_count: int
    """Number of tracks addressable on their own MIDI channel."""
    trigger_notes: bool = False
    """True when low notes trigger tracks directly (Digitakt notes 0-7 = tracks 1-8).

    Drives note logging and the presence of the track-trigger tools.
    """

    # Parameters
    parameters: dict[str, Parameter] = field(default_factory=dict)
    categories: dict[str, list[str]] = field(default_factory=dict)
    nrpn_name_lookup: Callable[[int, int], str | None] = lambda msb, lsb: None

    # Device-specific tools
    register_tools: Callable[[DeviceServer], None] | None = None
    """Hook called by build_server to add the tools unique to this device."""

    notes: str = ""
    """Short free-text quirks blurb surfaced on the status resource."""

    def parameter(self, name: str) -> Parameter | None:
        return self.parameters.get(name)
