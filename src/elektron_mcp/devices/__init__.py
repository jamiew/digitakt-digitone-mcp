"""Per-device specs and their device-specific tools."""

from elektron_mcp.devices.digitakt import SPEC as DIGITAKT
from elektron_mcp.devices.digitone import SPEC as DIGITONE

DEVICES = {spec.slug: spec for spec in (DIGITAKT, DIGITONE)}

__all__ = ["DEVICES", "DIGITAKT", "DIGITONE"]
