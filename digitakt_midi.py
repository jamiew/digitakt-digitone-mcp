#!/usr/bin/env python3
"""
Entry point for the Digitakt MIDI MCP Server.
Run with: uv run digitakt-midi
"""

import asyncio


def main():
    """Main entry point for the CLI."""
    from server import main as server_main
    asyncio.run(server_main())


if __name__ == "__main__":
    main()
