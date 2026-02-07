# macOS Mod Manager - Agent Guidelines

## Project Context

A Python-based mod manager for Cyberpunk 2077 on macOS. Provides web UI (FastAPI), TUI (Textual), and CLI for installing, managing, and validating mods. Integrates with Nexus Mods API for downloads.

## Current Status (Canonical)

See `docs/STATUS.md` for the current run-state and pointers to the active roadmap/status docs.

## Development Practices

### Python Standards

1. **Python 3.11+.** Use modern Python features: type hints, dataclasses, `match` statements.
2. **Async-first.** All I/O operations should be async; use `asyncio` and `aiohttp`.
3. **Type annotations.** All function signatures must have complete type hints.
4. **SQLAlchemy async.** Use `AsyncSession` for all database operations.

### Package Management

1. **UV for deps.** Use `uv` for fast dependency management; `uv.lock` is the source of truth.
2. **Requirements.txt.** Maintain for compatibility; sync with `pyproject.toml`.
3. **Virtual environment.** Always work in `.venv`; never install globally.

### Code Organization

1. **Separation of concerns.** API routes thin; business logic in `core/`; data access in `models/`.
2. **No circular imports.** Use dependency injection or late imports when needed.
3. **Config in one place.** All settings via `app/config.py` and environment variables.

## Architecture

### Directory Structure

```
app/
├── api/              # FastAPI route handlers
│   ├── mods.py       # Mod CRUD operations
│   ├── fomod.py      # FOMOD installer wizard
│   ├── nexus.py      # Nexus API integration
│   └── ...
├── core/             # Business logic
│   ├── mod_manager.py     # Central mod operations
│   ├── install_validator.py  # Installation with rollback
│   ├── nexus_api.py       # Nexus Mods client
│   ├── fomod_parser.py    # FOMOD XML parsing
│   └── game_detector.py   # Game path detection
├── models/           # SQLAlchemy models
├── templates/        # Jinja2 HTML templates
├── tui/              # Textual TUI application
│   ├── app.py        # Main TUI app
│   ├── screens/      # TUI screens
│   └── services/     # TUI service layer
└── main.py           # FastAPI app entry
scripts/              # Utility scripts
tests/                # Test suite
```

### Key Components

1. **ModManager** (`core/mod_manager.py`) - Central orchestrator for all mod operations.
2. **InstallValidator** (`core/install_validator.py`) - Atomic installation with filesystem rollback.
3. **NexusAPIClient** (`core/nexus_api.py`) - Nexus Mods API integration with caching.
4. **TUIModService** (`tui/services/`) - Bridge between TUI and core services.

## Code Standards

### Naming

1. **Files.** Lowercase with underscores: `mod_manager.py`, `nexus_api.py`.
2. **Classes.** PascalCase: `ModManager`, `NexusAPIClient`, `FomodParser`.
3. **Functions.** snake_case: `install_mod()`, `get_mod_files()`, `validate_installation()`.
4. **Constants.** SCREAMING_SNAKE: `NEXUS_API_BASE`, `DEFAULT_GAME_PATH`.

### Database

1. **Async sessions.** Use `get_async_session_context()` for transaction safety.
2. **Model naming.** Tables singular: `mod`, `profile`, `backup`.
3. **Migrations.** Use Alembic; never modify database directly.

### API Design

1. **RESTful routes.** `GET /mods`, `POST /mods/install`, `DELETE /mods/{id}`.
2. **JSON responses.** All API responses return JSON with consistent structure.
3. **Error handling.** Return appropriate HTTP codes; 4xx for client errors, 5xx for server.

### TUI Design

1. **Textual framework.** Use Textual's reactive system and widgets.
2. **Screen-based navigation.** Each major function is a separate screen.
3. **Background workers.** Long operations use `@work(thread=True)` decorator.
4. **Progress feedback.** Show progress bars for downloads and installations.

## Mod Compatibility

### macOS Compatibility Rules

1. **No Windows DLLs.** Mods containing `.dll` files without macOS equivalents are incompatible.
2. **Archive mods OK.** Pure `.archive` mods work without modification.
3. **RED4ext plugins.** Require macOS `.dylib` port; check `red4ext/plugins/`.
4. **Redscript mods.** Generally compatible; may need path adjustments.

### Compatibility Checking

```python
# In core/mod_manager.py
async def check_compatibility(mod_id: int) -> CompatibilityResult:
    # Scan for DLLs, check dependencies, verify paths
```

## Testing

### Running Tests

```bash
pytest tests/ -v
pytest tests/test_mod_manager.py -v  # Specific file
```

### Test Categories

1. **Unit tests.** Test individual functions in isolation.
2. **Integration tests.** Test API routes with database.
3. **TUI tests.** Use Textual's testing utilities.

### Mocking

1. **Mock Nexus API.** Don't hit real API in tests; use fixtures.
2. **Mock filesystem.** Use `tmp_path` fixture for file operations.
3. **Mock database.** Use in-memory SQLite for fast tests.

## CLI Usage

### Non-Interactive Mode

```bash
# Install mod
python -m app.tui.cli install --mod-id 3858 --auto-confirm

# Bulk install from file
python -m app.tui.cli bulk-install mods.txt --auto-confirm

# Check compatibility
python -m app.tui.cli check-compat https://nexusmods.com/cyberpunk2077/mods/3858
```

### Environment Variables

```bash
NEXUS_API_KEY=xxx          # Required for Nexus API
CP2077_GAME_PATH=/path     # Game installation path
NON_INTERACTIVE=1          # Skip all prompts
AUTO_CONFIRM=1             # Auto-accept confirmations
```

## Common Pitfalls

1. **Async context.** Don't call async functions from sync code without `asyncio.run()`.
2. **Session lifecycle.** Always use context manager for database sessions.
3. **File paths.** macOS uses `/` not `\`; use `pathlib.Path` everywhere.
4. **Archive handling.** RAR5 requires `unar` utility, not Python `rarfile`.
5. **Nexus rate limits.** Cache API responses; respect rate limit headers.

## Game Path Detection

The mod manager auto-detects Cyberpunk 2077 installation:

```
~/Library/Application Support/Steam/steamapps/common/Cyberpunk 2077/
```

### Important Paths

```
Cyberpunk 2077/
├── Cyberpunk2077.app/Contents/MacOS/   # Game binary
├── red4ext/
│   ├── plugins/                         # RED4ext plugins
│   └── cyberpunk2077_addresses.json    # Address database
├── r6/
│   ├── tweaks/                          # TweakXL tweaks
│   └── scripts/                         # Redscript mods
└── archive/pc/mod/                      # Archive mods
```

## Logging

1. **Structured logging.** Use Python `logging` module with appropriate levels.
2. **SQL logging.** Controlled via `SQL_ECHO` config; disable in production.
3. **Log files.** Stored in `data/logs/`; rotated daily.
