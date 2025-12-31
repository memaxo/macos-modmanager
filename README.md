# Cyberpunk 2077 macOS Mod Manager

Mod manager for Cyberpunk 2077 on macOS with automatic compatibility checking.

## Quick Start

```bash
pip install -r requirements.txt
alembic upgrade head
python run.py
```

Open `http://localhost:8000`

## Features

- macOS compatibility protection (blocks ArchiveXL, Codeware, RED4ext, CET)
- Nexus Mods integration
- Collection support
- Dependency resolution
- Conflict detection

## Tech Stack

FastAPI + HTMX + SQLite
