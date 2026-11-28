"""`digitakt-digitone-mcp <device>`: the command `uvx digitakt-digitone-mcp` runs.

uvx runs the script named after the package, so the published package needs one command
that picks a device. Each MCP Registry entry passes its device as the argument.
"""

import sys

from elektron_mcp.devices import digitakt, digitone

SERVERS = {"digitakt": digitakt.main, "digitone": digitone.main}


def main() -> None:
    args = sys.argv[1:]
    if len(args) != 1 or args[0] not in SERVERS:
        sys.exit(f"usage: digitakt-digitone-mcp {{{'|'.join(SERVERS)}}}")
    SERVERS[args[0]]()
