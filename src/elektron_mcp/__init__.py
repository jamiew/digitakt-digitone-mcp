"""MCP servers for controlling Elektron hardware over MIDI.

Each device gets its own server so you only load the tools for gear you own:

    digitakt-mcp    Elektron Digitakt (original)
    digitone-mcp    Elektron Digitone (original)

Devices are data (see `elektron_mcp.device.DeviceSpec`) over one shared server
implementation, so supporting another machine means describing it, not forking.
"""

__version__ = "0.3.0"
