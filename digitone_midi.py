"""
Entry point for the Digitone MIDI MCP Server.
Run with: uv run digitone-midi
"""


def main():
    from server_digitone import main as digitone_main

    digitone_main()


if __name__ == "__main__":
    main()
