# Hardware scripts

Manual scripts that need a real device connected. They are **not** part of the test
suite — `pytest` only collects `tests/`.

```bash
uv run python scripts/hardware/test_transport.py
```

These predate the `src/elektron_mcp/` refactor and talk to `mido` directly rather than
going through the package. They work, but they are not maintained to the same standard
as the package and are not linted (see `extend-exclude` in `pyproject.toml`).
