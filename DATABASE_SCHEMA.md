# Database Schema Design - SQLite

## Overview
SQLite database for local mod management with support for mods, collections, dependencies, compatibility, and user preferences.

## Tables

### 1. `games`
Stores detected game installations.

```sql
CREATE TABLE games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    game_id TEXT NOT NULL UNIQUE,  -- e.g., 'cyberpunk2077'
    version TEXT,
    install_path TEXT NOT NULL,
    launcher_type TEXT NOT NULL,  -- 'steam', 'gog', 'epic', 'standalone'
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    UNIQUE(game_id, install_path)
);

CREATE INDEX idx_games_active ON games(is_active);
CREATE INDEX idx_games_game_id ON games(game_id);
```

### 2. `mods`
Core mod information.

```sql
CREATE TABLE mods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nexus_mod_id INTEGER UNIQUE,  -- Nexus Mods ID
    name TEXT NOT NULL,
    author TEXT,
    description TEXT,
    version TEXT,
    game_id TEXT NOT NULL,
    mod_type TEXT,  -- 'redscript', 'archive', 'redmod', 'mixed'
    install_path TEXT NOT NULL,  -- Relative to game directory
    file_hash TEXT,  -- SHA256 hash of mod archive
    file_size INTEGER,  -- Size in bytes
    download_url TEXT,
    nexus_url TEXT,
    thumbnail_url TEXT,
    is_enabled BOOLEAN DEFAULT 1,
    is_active BOOLEAN DEFAULT 1,  -- Not deleted
    install_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_date TIMESTAMP,
    last_checked TIMESTAMP,
    metadata JSON,  -- Additional metadata as JSON
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE INDEX idx_mods_nexus_id ON mods(nexus_mod_id);
CREATE INDEX idx_mods_game_id ON mods(game_id);
CREATE INDEX idx_mods_enabled ON mods(is_enabled);
CREATE INDEX idx_mods_active ON mods(is_active);
CREATE INDEX idx_mods_type ON mods(mod_type);
```

### 3. `mod_files`
Individual files within mods.

```sql
CREATE TABLE mod_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,  -- Relative path within mod
    file_type TEXT,  -- 'reds', 'archive', 'dll', 'config', etc.
    file_hash TEXT,
    file_size INTEGER,
    install_path TEXT,  -- Where file is installed in game directory
    FOREIGN KEY (mod_id) REFERENCES mods(id) ON DELETE CASCADE,
    UNIQUE(mod_id, file_path)
);

CREATE INDEX idx_mod_files_mod_id ON mod_files(mod_id);
CREATE INDEX idx_mod_files_type ON mod_files(file_type);
CREATE INDEX idx_mod_files_install_path ON mod_files(install_path);
```

### 4. `mod_dependencies`
Mod dependency relationships.

```sql
CREATE TABLE mod_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_id INTEGER NOT NULL,
    dependency_name TEXT NOT NULL,  -- e.g., 'redscript', 'ArchiveXL', 'Codeware'
    dependency_type TEXT NOT NULL,  -- 'required', 'optional', 'incompatible'
    min_version TEXT,
    max_version TEXT,
    nexus_mod_id INTEGER,  -- If dependency is a Nexus mod
    is_satisfied BOOLEAN DEFAULT 0,
    FOREIGN KEY (mod_id) REFERENCES mods(id) ON DELETE CASCADE
);

CREATE INDEX idx_mod_deps_mod_id ON mod_dependencies(mod_id);
CREATE INDEX idx_mod_deps_name ON mod_dependencies(dependency_name);
CREATE INDEX idx_mod_deps_satisfied ON mod_dependencies(is_satisfied);
```

### 5. `mod_conflicts`
File conflicts between mods.

```sql
CREATE TABLE mod_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,  -- Conflicted file path
    mod_id_1 INTEGER NOT NULL,
    mod_id_2 INTEGER NOT NULL,
    conflict_type TEXT NOT NULL,  -- 'file_overwrite', 'load_order', 'incompatible'
    severity TEXT NOT NULL,  -- 'critical', 'warning', 'info'
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved BOOLEAN DEFAULT 0,
    resolution_method TEXT,  -- 'load_order', 'disabled', 'manual'
    FOREIGN KEY (mod_id_1) REFERENCES mods(id) ON DELETE CASCADE,
    FOREIGN KEY (mod_id_2) REFERENCES mods(id) ON DELETE CASCADE,
    CHECK(mod_id_1 != mod_id_2)
);

CREATE INDEX idx_mod_conflicts_file_path ON mod_conflicts(file_path);
CREATE INDEX idx_mod_conflicts_mods ON mod_conflicts(mod_id_1, mod_id_2);
CREATE INDEX idx_mod_conflicts_resolved ON mod_conflicts(resolved);
CREATE INDEX idx_mod_conflicts_severity ON mod_conflicts(severity);
```

### 6. `mod_load_order`
Mod load order/priority.

```sql
CREATE TABLE mod_load_order (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_id INTEGER NOT NULL,
    game_id TEXT NOT NULL,
    profile_id INTEGER,  -- NULL for default profile
    priority INTEGER NOT NULL,  -- Lower = loaded first
    FOREIGN KEY (mod_id) REFERENCES mods(id) ON DELETE CASCADE,
    FOREIGN KEY (game_id) REFERENCES games(game_id),
    FOREIGN KEY (profile_id) REFERENCES mod_profiles(id) ON DELETE CASCADE,
    UNIQUE(mod_id, game_id, profile_id)
);

CREATE INDEX idx_load_order_game_profile ON mod_load_order(game_id, profile_id);
CREATE INDEX idx_load_order_priority ON mod_load_order(priority);
```

### 7. `mod_profiles`
Mod profiles for different configurations.

```sql
CREATE TABLE mod_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    game_id TEXT NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE INDEX idx_profiles_game_id ON mod_profiles(game_id);
CREATE INDEX idx_profiles_default ON mod_profiles(is_default);
```

### 8. `profile_mods`
Mods associated with profiles.

```sql
CREATE TABLE profile_mods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    mod_id INTEGER NOT NULL,
    is_enabled BOOLEAN DEFAULT 1,
    FOREIGN KEY (profile_id) REFERENCES mod_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (mod_id) REFERENCES mods(id) ON DELETE CASCADE,
    UNIQUE(profile_id, mod_id)
);

CREATE INDEX idx_profile_mods_profile ON profile_mods(profile_id);
CREATE INDEX idx_profile_mods_mod ON profile_mods(mod_id);
```

### 9. `collections`
Nexus Mods collections.

```sql
CREATE TABLE collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nexus_collection_id TEXT UNIQUE,  -- Collection ID from Nexus
    name TEXT NOT NULL,
    author TEXT,
    description TEXT,
    game_id TEXT NOT NULL,
    version TEXT,
    mod_count INTEGER DEFAULT 0,
    thumbnail_url TEXT,
    nexus_url TEXT,
    collection_data JSON,  -- Full collection JSON
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    installed_at TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE INDEX idx_collections_nexus_id ON collections(nexus_collection_id);
CREATE INDEX idx_collections_game_id ON collections(game_id);
```

### 10. `collection_mods`
Mods in collections.

```sql
CREATE TABLE collection_mods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL,
    nexus_mod_id INTEGER NOT NULL,
    nexus_file_id INTEGER,
    mod_id INTEGER,  -- Reference to installed mod (if installed)
    is_required BOOLEAN DEFAULT 1,
    install_order INTEGER,
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (mod_id) REFERENCES mods(id) ON DELETE SET NULL
);

CREATE INDEX idx_collection_mods_collection ON collection_mods(collection_id);
CREATE INDEX idx_collection_mods_mod ON collection_mods(mod_id);
```

### 11. `compatibility_rules`
Compatibility rules for mods.

```sql
CREATE TABLE compatibility_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_id INTEGER,
    nexus_mod_id INTEGER,
    rule_type TEXT NOT NULL,  -- 'compatible', 'incompatible', 'requires', 'conflicts_with'
    target_mod_id INTEGER,
    target_nexus_mod_id INTEGER,
    target_dependency TEXT,  -- e.g., 'ArchiveXL', 'Codeware'
    platform TEXT,  -- 'macos', 'windows', 'linux', NULL for all
    game_version_min TEXT,
    game_version_max TEXT,
    severity TEXT DEFAULT 'warning',  -- 'critical', 'warning', 'info'
    description TEXT,
    source TEXT DEFAULT 'user',  -- 'user', 'community', 'official', 'auto'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified BOOLEAN DEFAULT 0,
    FOREIGN KEY (mod_id) REFERENCES mods(id) ON DELETE CASCADE,
    FOREIGN KEY (target_mod_id) REFERENCES mods(id) ON DELETE CASCADE)
);

CREATE INDEX idx_compat_rules_mod ON compatibility_rules(mod_id);
CREATE INDEX idx_compat_rules_target ON compatibility_rules(target_mod_id);
CREATE INDEX idx_compat_rules_type ON compatibility_rules(rule_type);
CREATE INDEX idx_compat_rules_platform ON compatibility_rules(platform);
```

### 12. `mod_installations`
Installation history and backups.

```sql
CREATE TABLE mod_installations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_id INTEGER NOT NULL,
    install_type TEXT NOT NULL,  -- 'install', 'update', 'uninstall'
    backup_path TEXT,  -- Path to backup
    install_path TEXT NOT NULL,
    file_hash_before TEXT,
    file_hash_after TEXT,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rollback_available BOOLEAN DEFAULT 0,
    FOREIGN KEY (mod_id) REFERENCES mods(id) ON DELETE CASCADE
);

CREATE INDEX idx_installations_mod ON mod_installations(mod_id);
CREATE INDEX idx_installations_type ON mod_installations(install_type);
CREATE INDEX idx_installations_date ON mod_installations(installed_at);
```

### 13. `settings`
Application settings.

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT DEFAULT 'string',  -- 'string', 'integer', 'boolean', 'json'
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 14. `nexus_api_cache`
Cache for Nexus Mods API responses.

```sql
CREATE TABLE nexus_api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT NOT NULL UNIQUE,
    cache_data JSON NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nexus_cache_key ON nexus_api_cache(cache_key);
CREATE INDEX idx_nexus_cache_expires ON nexus_api_cache(expires_at);
```

### 15. `mod_analytics`
Usage analytics for mods.

```sql
CREATE TABLE mod_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,  -- 'install', 'enable', 'disable', 'uninstall', 'error'
    event_data JSON,
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mod_id) REFERENCES mods(id) ON DELETE CASCADE
);

CREATE INDEX idx_analytics_mod ON mod_analytics(mod_id);
CREATE INDEX idx_analytics_type ON mod_analytics(event_type);
CREATE INDEX idx_analytics_date ON mod_analytics(occurred_at);
```

## Views

### `mod_compatibility_view`
View showing mod compatibility status.

```sql
CREATE VIEW mod_compatibility_view AS
SELECT 
    m.id,
    m.name,
    m.mod_type,
    m.is_enabled,
    COUNT(DISTINCT CASE WHEN md.dependency_type = 'required' AND md.is_satisfied = 0 THEN md.id END) as missing_required_deps,
    COUNT(DISTINCT CASE WHEN cr.rule_type = 'incompatible' AND cr.platform = 'macos' THEN cr.id END) as incompatibilities,
    COUNT(DISTINCT mc.id) as conflicts
FROM mods m
LEFT JOIN mod_dependencies md ON m.id = md.mod_id
LEFT JOIN compatibility_rules cr ON m.id = cr.mod_id
LEFT JOIN mod_conflicts mc ON m.id = mc.mod_id_1 OR m.id = mc.mod_id_2
WHERE m.is_active = 1
GROUP BY m.id;
```

## Triggers

### Update mod update_date on file changes
```sql
CREATE TRIGGER update_mod_timestamp
AFTER UPDATE ON mods
FOR EACH ROW
WHEN NEW.update_date IS NULL OR NEW.update_date < OLD.update_date
BEGIN
    UPDATE mods SET update_date = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
```

### Clean expired cache entries
```sql
CREATE TRIGGER clean_expired_cache
AFTER INSERT ON nexus_api_cache
BEGIN
    DELETE FROM nexus_api_cache WHERE expires_at < CURRENT_TIMESTAMP;
END;
```

## Initial Data

### Default settings
```sql
INSERT INTO settings (key, value, value_type, description) VALUES
('nexus_api_key', '', 'string', 'Nexus Mods API key'),
('auto_check_updates', 'true', 'boolean', 'Automatically check for mod updates'),
('backup_before_install', 'true', 'boolean', 'Create backup before installing mods'),
('macos_compatibility_strict', 'true', 'boolean', 'Strict macOS compatibility checking'),
('game_install_path', '', 'string', 'Default game installation path'),
('mod_install_path', 'r6/scripts', 'string', 'Default mod installation path'),
('theme', 'dark', 'string', 'UI theme preference');
```
