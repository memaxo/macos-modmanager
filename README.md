# macOS Mod Manager (Legacy)

Python-based mod manager for Cyberpunk 2077 on macOS.

**Status:** Superseded by [CyberMod Studio](../cybermod-studio).

## What it does

Web UI (FastAPI), TUI (Textual), and CLI for installing and managing Cyberpunk 2077 mods. Integrates with Nexus Mods API. This project has been superseded by CyberMod Studio (native Swift/SwiftUI) but remains available for reference and its profiling/analysis scripts.

## Still useful

- `scripts/` — Game binary analysis and profiling tools
- `docs/` — RT optimization research, GPU profiling findings, binary analysis reports

## Setup

```bash
uv sync
python -m app.main  # Web UI on localhost:8000
```

## Related projects

| Project | Description |
|---------|-------------|
| [CyberMod Studio](../cybermod-studio) | Native replacement |
