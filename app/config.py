from pydantic_settings import BaseSettings
from pathlib import Path
import os


class Settings(BaseSettings):
    app_name: str = "Cyberpunk 2077 macOS Mod Manager"
    debug: bool = True
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./mods.db"
    
    # Nexus Mods API
    nexus_api_key: str = ""
    nexus_api_base_url: str = "https://api.nexusmods.com/v1"
    
    # Paths
    data_dir: Path = Path.home() / ".cyberpunk-modmanager"
    cache_dir: Path = Path.home() / ".cyberpunk-modmanager" / "cache"
    backups_dir: Path = Path.home() / ".cyberpunk-modmanager" / "backups"
    
    # macOS Compatibility
    strict_compatibility: bool = True
    auto_remove_quarantine: bool = True
    
    # Mod Settings
    default_mod_path: str = "r6/scripts"
    backup_before_install: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
