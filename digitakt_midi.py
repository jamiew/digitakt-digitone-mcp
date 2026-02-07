#!/usr/bin/env python3
"""
Entry point for the Digitakt MIDI MCP Server.
Run with: uv run digitakt-midi

Uses FastMCP for cleaner code and automatic schema generation.
Set DIGITAKT_USE_LEGACY=1 to use the original server.py implementation.
"""

import os


def main():
    """Main entry point for the CLI."""
    if os.environ.get("DIGITAKT_USE_LEGACY") == "1":
        # Use original server implementation
        import asyncio
        from server import main as server_main
        asyncio.run(server_main())
    else:
        # Use FastMCP implementation (default)
        from server_fastmcp import main as fastmcp_main
        fastmcp_main()


if __name__ == "__main__":
    main()
