# macOS Mod Manager — Status

> **Last updated:** 2026-02-01  

## What this repo is

A Python-based mod manager for Cyberpunk 2077 on macOS with:

- web UI (FastAPI)
- TUI (Textual)
- CLI utilities
- macOS-focused compatibility checks

## Canonical “what’s happening right now”

- **Current run status (profiling / optimization work):** `docs/CURRENT_RUN_STATUS.md`
- **Execution status / plan tracking:** `docs/EXECUTION_STATUS.md`
- **Roadmap:** `docs/IMPROVEMENT_ROADMAP.md`

## Quick start (developer)

This repo supports both `uv` and `pip` workflows.

### Option A: uv (recommended)

```bash
uv sync
alembic upgrade head
python run.py
```

### Option B: pip

```bash
pip install -r requirements.txt
alembic upgrade head
python run.py
```

Then open `http://localhost:8000`.

## Test entry points

- Test suite overview: `tests/README.md`

