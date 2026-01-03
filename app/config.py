from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional
import os


class Settings(BaseSettings):
    app_name: str = "Cyberpunk 2077 macOS Mod Manager"
    debug: bool = False  # Set via DEBUG=1 env var
    sql_echo: bool = False  # Set via SQL_ECHO=1 env var for SQL logging
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./mods.db"
    
    # Nexus Mods API
    nexus_api_key: str = ""
    nexus_api_base_url: str = "https://api.nexusmods.com/v1"
    
    # Game Configuration
    game_id: str = "cyberpunk2077"
    game_domain: str = "cyberpunk2077"
    game_name: str = "Cyberpunk 2077"
    
    # User-configurable game path (overrides auto-detection)
    # Can be set via environment variable CUSTOM_GAME_PATH or through the UI
    custom_game_path: Optional[str] = None
    
    # Paths
    @property
    def base_data_dir(self) -> Path:
        return Path.home() / ".macos-modmanager"
    
    @property
    def game_data_dir(self) -> Path:
        return self.base_data_dir / self.game_id
    
    @property
    def custom_game_path_resolved(self) -> Optional[Path]:
        """Get resolved custom game path if set and valid"""
        if self.custom_game_path:
            path = Path(self.custom_game_path)
            if path.exists():
                return path
        return None

    data_dir: Path = Path.home() / ".macos-modmanager" / "cyberpunk2077"
    cache_dir: Path = Path.home() / ".macos-modmanager" / "cyberpunk2077" / "cache"
    backups_dir: Path = Path.home() / ".macos-modmanager" / "cyberpunk2077" / "backups"
    staging_dir: Path = Path.home() / ".macos-modmanager" / "cyberpunk2077" / "staging"
    
    # macOS Compatibility
    strict_compatibility: bool = True
    auto_remove_quarantine: bool = True
    
    # Mod Paths (macOS structure)
    # Redscript mods go to r6/scripts/
    default_mod_path: str = "r6/scripts"
    # RED4ext plugins go to red4ext/plugins/
    red4ext_plugins_path: str = "red4ext/plugins"
    # TweakXL tweaks go to r6/tweaks/
    tweakxl_tweaks_path: str = "r6/tweaks"
    # ArchiveXL mods go to archive/pc/mod/
    archivexl_mods_path: str = "archive/pc/mod"
    
    # Mod Settings
    backup_before_install: bool = True
    auto_check_updates: bool = True
    
    # macOS-ported mod framework repositories
    macos_red4ext_repo: str = "https://github.com/memaxo/RED4ext-macos"
    macos_tweakxl_repo: str = "https://github.com/memaxo/cp2077-tweak-xl-macos"
    macos_archivexl_repo: str = "https://github.com/memaxo/cp2077-archive-xl-macos"
    macos_sdk_repo: str = "https://github.com/memaxo/RED4ext.SDK-macos"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
    
    def set_custom_game_path(self, path: str) -> bool:
        """Set custom game path (validates it exists)"""
        p = Path(path)
        if p.exists():
            self.custom_game_path = str(p)
            return True
        return False


settings = Settings()
