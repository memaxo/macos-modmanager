# Architecture Design - FastAPI + HTMX + SQLite

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Browser (HTMX)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Mod List   │  │  Collections  │  │   Settings   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP/HTMX
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    FastAPI Backend                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              API Routes Layer                         │   │
│  │  /api/mods, /api/collections, /api/compatibility      │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │            Business Logic Layer                       │   │
│  │  ModManager, CompatibilityChecker, NexusAPI          │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │            Data Access Layer                          │   │
│  │  Database, FileSystem, Cache                         │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐   ┌────────▼────────┐  ┌──────▼──────┐
│   SQLite DB  │   │  File System    │  │   Cache     │
│  (mods.db)   │   │  (Game Dir)     │  │  (Redis/    │
│              │   │                 │  │   Memory)    │
└──────────────┘   └─────────────────┘  └────────────┘
```

## Technology Stack

### Backend
- **FastAPI**: Modern, fast web framework
- **SQLAlchemy**: ORM for database operations
- **aiosqlite**: Async SQLite driver
- **Pydantic**: Data validation and settings
- **httpx**: Async HTTP client for Nexus API
- **aiofiles**: Async file operations
- **python-multipart**: File upload handling

### Frontend
- **HTMX**: Dynamic HTML updates
- **Jinja2**: Template engine
- **Alpine.js**: Lightweight JavaScript framework (optional)
- **Tailwind CSS**: Utility-first CSS framework
- **Hyperscript**: Event handling (optional)

### Database
- **SQLite**: Local database
- **Alembic**: Database migrations

### Additional Libraries
- **py7zr**: Archive extraction
- **rarfile**: RAR archive support
- **hashlib**: File hashing
- **watchdog**: File system monitoring

## Project Structure

```
macos-modmanager/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Configuration settings
│   │
│   ├── api/                    # API routes
│   │   ├── __init__.py
│   │   ├── mods.py             # Mod management endpoints
│   │   ├── collections.py      # Collection endpoints
│   │   ├── compatibility.py    # Compatibility checking
│   │   ├── games.py            # Game detection
│   │   └── files.py            # File operations
│   │
│   ├── core/                   # Core business logic
│   │   ├── __init__.py
│   │   ├── mod_manager.py      # Mod installation/management
│   │   ├── compatibility.py    # Compatibility checking logic
│   │   ├── nexus_api.py        # Nexus Mods API client
│   │   ├── game_detector.py    # Game installation detection
│   │   ├── dependency_resolver.py  # Dependency resolution
│   │   └── conflict_detector.py    # Conflict detection
│   │
│   ├── models/                 # Database models
│   │   ├── __init__.py
│   │   ├── mod.py
│   │   ├── collection.py
│   │   ├── compatibility.py
│   │   └── game.py
│   │
│   ├── database/               # Database setup
│   │   ├── __init__.py
│   │   ├── base.py            # Base model
│   │   ├── session.py          # Database session
│   │   └── migrations/         # Alembic migrations
│   │
│   ├── services/               # Service layer
│   │   ├── __init__.py
│   │   ├── archive_service.py  # Archive extraction
│   │   ├── file_service.py     # File operations
│   │   ├── cache_service.py    # Caching
│   │   └── notification_service.py  # Notifications
│   │
│   ├── utils/                  # Utilities
│   │   ├── __init__.py
│   │   ├── file_utils.py       # File utilities
│   │   ├── hash_utils.py       # Hashing utilities
│   │   ├── path_utils.py       # Path utilities (macOS)
│   │   └── validators.py       # Validation utilities
│   │
│   ├── templates/              # Jinja2 templates
│   │   ├── base.html
│   │   ├── mods/
│   │   │   ├── list.html
│   │   │   ├── detail.html
│   │   │   └── install.html
│   │   ├── collections/
│   │   │   ├── list.html
│   │   │   └── import.html
│   │   └── compatibility/
│   │       └── checker.html
│   │
│   └── static/                 # Static files
│       ├── css/
│       ├── js/
│       └── images/
│
├── tests/                      # Tests
│   ├── __init__.py
│   ├── test_api/
│   ├── test_core/
│   └── test_utils/
│
├── alembic/                    # Database migrations
├── requirements.txt
├── README.md
├── FEATURES.md
├── DATABASE_SCHEMA.md
└── ARCHITECTURE.md
```

## API Endpoints Design

### Mod Management
```
GET    /api/mods                    # List all mods
GET    /api/mods/{mod_id}          # Get mod details
POST   /api/mods                   # Install new mod
PUT    /api/mods/{mod_id}          # Update mod
DELETE /api/mods/{mod_id}          # Uninstall mod
POST   /api/mods/{mod_id}/enable   # Enable mod
POST   /api/mods/{mod_id}/disable  # Disable mod
GET    /api/mods/{mod_id}/files    # List mod files
POST   /api/mods/check-updates     # Check for updates
```

### Collections
```
GET    /api/collections            # List collections
GET    /api/collections/{id}       # Get collection details
POST   /api/collections/import     # Import collection
POST   /api/collections/{id}/install  # Install collection
DELETE /api/collections/{id}       # Delete collection
```

### Compatibility
```
GET    /api/compatibility/check/{mod_id}     # Check mod compatibility
POST   /api/compatibility/scan               # Scan all mods
GET    /api/compatibility/conflicts          # Get conflicts
GET    /api/compatibility/dependencies       # Get dependencies
POST   /api/compatibility/resolve/{conflict_id}  # Resolve conflict
```

### Games
```
GET    /api/games                  # List detected games
POST   /api/games/detect          # Detect games
GET    /api/games/{game_id}       # Get game details
PUT    /api/games/{game_id}       # Update game settings
```

### Files
```
POST   /api/files/upload          # Upload mod file
GET    /api/files/{path}         # Get file info
DELETE /api/files/{path}          # Delete file
POST   /api/files/extract         # Extract archive
```

## HTMX Integration Patterns

### Partial Page Updates
```html
<!-- Mod list with HTMX -->
<div id="mod-list" hx-get="/api/mods" hx-trigger="load, refresh from:body">
    <!-- Mod items loaded via HTMX -->
</div>

<!-- Enable/disable mod -->
<button hx-post="/api/mods/123/enable" 
        hx-target="#mod-list" 
        hx-swap="outerHTML">
    Enable
</button>
```

### Form Submissions
```html
<!-- Install mod form -->
<form hx-post="/api/mods" 
      hx-target="#mod-list" 
      hx-swap="beforeend"
      hx-indicator="#loading">
    <input type="file" name="mod_file" />
    <button type="submit">Install</button>
</form>
```

### Infinite Scroll
```html
<!-- Paginated mod list -->
<div hx-get="/api/mods?page=1" 
     hx-trigger="revealed" 
     hx-swap="afterend">
    <!-- Mod items -->
</div>
```

### Real-time Updates
```html
<!-- Progress indicator -->
<div hx-get="/api/mods/123/status" 
     hx-trigger="every 1s" 
     hx-swap="innerHTML">
    Loading...
</div>
```

## Compatibility Checking System

### Pre-Installation Check Flow
```
1. User selects mod to install
2. Extract mod archive (temporary)
3. Scan mod files:
   - Check for .reds files (compatible)
   - Check for ArchiveXL references (incompatible)
   - Check for Codeware dependencies (incompatible)
   - Check for RED4ext requirements (incompatible)
   - Check for CET requirements (incompatible)
4. Check mod metadata:
   - Parse mod description for dependencies
   - Check Nexus Mods API for requirements
   - Query compatibility database
5. Check conflicts:
   - Compare file paths with installed mods
   - Check load order conflicts
   - Check known incompatibilities
6. Generate compatibility report
7. If compatible: proceed with installation
8. If incompatible: show warning/error
```

### Compatibility Database Structure
```python
# Compatibility rules stored in database
{
    "mod_id": 12345,
    "rules": [
        {
            "type": "incompatible",
            "target": "ArchiveXL",
            "platform": "macos",
            "severity": "critical",
            "reason": "ArchiveXL requires RED4ext which is not supported on macOS"
        },
        {
            "type": "requires",
            "target": "redscript",
            "min_version": "0.5.29",
            "platform": "macos"
        }
    ]
}
```

## File System Operations

### macOS-Specific Handling
```python
# Path utilities
def get_steam_install_path():
    return Path.home() / "Library/Application Support/Steam/steamapps/common/Cyberpunk 2077"

def remove_quarantine_flag(path: Path):
    """Remove macOS quarantine attribute"""
    subprocess.run(["xattr", "-d", "com.apple.quarantine", str(path)])

def make_executable(path: Path):
    """Make file executable"""
    path.chmod(0o755)
```

### Mod Installation Flow
```python
async def install_mod(mod_file: Path, game_path: Path):
    # 1. Extract archive
    extract_path = await extract_archive(mod_file)
    
    # 2. Detect mod structure
    mod_structure = detect_mod_structure(extract_path)
    
    # 3. Check compatibility
    compatibility = await check_compatibility(mod_structure)
    if not compatibility.is_compatible:
        raise CompatibilityError(compatibility.reasons)
    
    # 4. Backup existing files
    await backup_conflicting_files(game_path, mod_structure)
    
    # 5. Install files
    install_path = game_path / "r6/scripts"
    await copy_mod_files(extract_path, install_path)
    
    # 6. Remove quarantine flags (macOS)
    if sys.platform == "darwin":
        remove_quarantine_flag(install_path)
    
    # 7. Update database
    await save_mod_to_db(mod_structure, install_path)
    
    # 8. Cleanup
    await cleanup_temp_files(extract_path)
```

## Caching Strategy

### Cache Layers
1. **Memory Cache**: Fast, in-process (mod metadata, compatibility rules)
2. **SQLite Cache**: Persistent (Nexus API responses, mod data)
3. **File Cache**: Large data (downloaded mods, thumbnails)

### Cache Invalidation
- Mod updates: Invalidate mod cache
- Compatibility changes: Invalidate compatibility cache
- Game version changes: Invalidate all caches

## Error Handling

### Error Types
- `CompatibilityError`: Mod incompatible with macOS
- `DependencyError`: Missing required dependencies
- `ConflictError`: File conflicts detected
- `InstallationError`: Installation failed
- `NexusAPIError`: Nexus API issues

### Error Response Format
```json
{
    "error": {
        "type": "CompatibilityError",
        "message": "Mod requires ArchiveXL which is not compatible with macOS",
        "details": {
            "mod_id": 12345,
            "incompatible_dependencies": ["ArchiveXL"],
            "severity": "critical"
        }
    }
}
```

## Security Considerations

### API Key Storage
- Store Nexus API keys encrypted in SQLite
- Use environment variables for sensitive data
- Never expose API keys in frontend

### File Operations
- Validate file paths (prevent directory traversal)
- Sanitize file names
- Check file sizes before extraction
- Verify file hashes

### Input Validation
- Validate all user inputs with Pydantic
- Sanitize file paths
- Check file types before processing

## Performance Optimizations

### Database
- Use indexes on frequently queried columns
- Use connection pooling
- Batch database operations
- Use WAL mode for SQLite

### File Operations
- Use async file operations (aiofiles)
- Parallel file processing where possible
- Stream large files
- Cache file metadata

### API Calls
- Cache Nexus API responses
- Use rate limiting
- Batch API requests
- Background job processing

## Deployment

### Development
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production
- Use Gunicorn with Uvicorn workers
- Set up reverse proxy (nginx)
- Enable HTTPS
- Set up logging
- Monitor performance
