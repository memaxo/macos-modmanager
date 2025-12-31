from pathlib import Path
from app.utils.path_utils import get_steam_install_path, get_gog_install_path


async def detect_cyberpunk_installations() -> list[dict]:
    """Detect Cyberpunk 2077 installations on macOS"""
    installations = []
    
    # Check Steam
    steam_path = get_steam_install_path()
    if steam_path.exists() and (steam_path / "Cyberpunk2077.app").exists():
        installations.append({
            "path": str(steam_path),
            "launcher": "steam",
            "version": None  # TODO: Extract version
        })
    
    # Check GOG
    gog_path = get_gog_install_path()
    if gog_path.exists() and (gog_path / "Cyberpunk2077.app").exists():
        installations.append({
            "path": str(gog_path),
            "launcher": "gog",
            "version": None
        })
    
    return installations
