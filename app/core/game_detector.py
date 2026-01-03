from pathlib import Path
import plistlib
import logging
from typing import List, TypedDict, Optional
from app.utils.path_utils import (
    get_steam_install_path, 
    get_gog_install_path, 
    get_all_possible_game_paths,
    validate_game_path
)
from app.config import settings

logger = logging.getLogger(__name__)


class GameInstallationDict(TypedDict):
    path: str
    launcher: str
    version: Optional[str]


async def detect_game_installations(app_bundle_name: str = "Cyberpunk2077.app") -> List[GameInstallationDict]:
    """
    Detect game installations on macOS.
    
    Priority order:
    1. User-configured custom path (from settings)
    2. Steam installation
    3. GOG installation
    4. Other known locations (external drives, alternative launchers)
    
    Args:
        app_bundle_name: The app bundle name to look for (e.g., "Cyberpunk2077.app")
        
    Returns:
        List of detected game installations
    """
    installations: List[GameInstallationDict] = []
    seen_paths: set[str] = set()  # Avoid duplicates
    
    # 1. Check user-configured custom path FIRST (highest priority)
    custom_path = settings.custom_game_path_resolved
    if custom_path:
        custom_app = custom_path / app_bundle_name
        if custom_app.exists():
            version = _get_app_version(custom_app)
            installations.append(GameInstallationDict(
                path=str(custom_path),
                launcher="custom",
                version=version
            ))
            seen_paths.add(str(custom_path))
            logger.info(f"Using custom game path: {custom_path}")
        else:
            logger.warning(f"Custom game path configured but app not found: {custom_path}/{app_bundle_name}")
    
    # 2. Check Steam (primary)
    steam_path = get_steam_install_path()
    if str(steam_path) not in seen_paths:
        steam_app = steam_path / app_bundle_name
        if steam_path.exists() and steam_app.exists():
            version = _get_app_version(steam_app)
            installations.append(GameInstallationDict(
                path=str(steam_path),
                launcher="steam",
                version=version
            ))
            seen_paths.add(str(steam_path))
    
    # 3. Check GOG (primary)
    gog_path = get_gog_install_path()
    if str(gog_path) not in seen_paths:
        gog_app = gog_path / app_bundle_name
        if gog_path.exists() and gog_app.exists():
            version = _get_app_version(gog_app)
            installations.append(GameInstallationDict(
                path=str(gog_path),
                launcher="gog",
                version=version
            ))
            seen_paths.add(str(gog_path))
    
    # 4. Check all other known paths (fallbacks)
    for path in get_all_possible_game_paths():
        if str(path) not in seen_paths:
            app_path = path / app_bundle_name
            if path.exists() and app_path.exists():
                version = _get_app_version(app_path)
                # Determine launcher type from path
                launcher = _detect_launcher_type(path)
                installations.append(GameInstallationDict(
                    path=str(path),
                    launcher=launcher,
                    version=version
                ))
                seen_paths.add(str(path))
                logger.info(f"Found game installation at fallback path: {path} ({launcher})")
    
    if not installations:
        logger.warning(f"No {app_bundle_name} installations found in any known location")
    
    return installations


async def detect_cyberpunk_installations() -> List[GameInstallationDict]:
    """Convenience function to detect Cyberpunk 2077 installations"""
    return await detect_game_installations("Cyberpunk2077.app")


async def get_primary_game_path(app_bundle_name: str = "Cyberpunk2077.app") -> Optional[Path]:
    """
    Get the primary game installation path.
    
    Returns the first detected installation (respects priority order).
    
    Args:
        app_bundle_name: The app bundle name to look for
        
    Returns:
        Path to game installation or None if not found
    """
    installations = await detect_game_installations(app_bundle_name)
    if installations:
        return Path(installations[0]["path"])
    return None


def _get_app_version(app_path: Path) -> Optional[str]:
    """Extract version from macOS .app bundle Info.plist"""
    info_plist = app_path / "Contents" / "Info.plist"
    if not info_plist.exists():
        return None
    
    try:
        with open(info_plist, "rb") as f:
            plist = plistlib.load(f)
            # Try common version keys
            return plist.get("CFBundleShortVersionString") or plist.get("CFBundleVersion")
    except Exception as e:
        logger.debug(f"Could not read app version from {info_plist}: {e}")
        return None


def _detect_launcher_type(path: Path) -> str:
    """Detect the launcher type from the installation path"""
    path_str = str(path).lower()
    
    if "steam" in path_str:
        return "steam"
    elif "gog" in path_str:
        return "gog"
    elif "heroic" in path_str:
        return "heroic"
    elif "crossover" in path_str or "wine" in path_str:
        return "crossover"
    elif "/volumes/" in path_str:
        return "external"
    else:
        return "unknown"


async def validate_and_set_custom_path(path_str: str, app_bundle_name: str = "Cyberpunk2077.app") -> tuple[bool, str]:
    """
    Validate and set a custom game path.
    
    Args:
        path_str: The path string to validate
        app_bundle_name: Expected app bundle name
        
    Returns:
        Tuple of (success, message)
    """
    path = Path(path_str)
    
    if not path.exists():
        return (False, f"Path does not exist: {path}")
    
    if not path.is_dir():
        return (False, f"Path is not a directory: {path}")
    
    app_path = path / app_bundle_name
    if not app_path.exists():
        return (False, f"Game not found at path. Expected to find: {app_path}")
    
    # Valid - update settings
    settings.custom_game_path = str(path)
    logger.info(f"Custom game path set to: {path}")
    
    return (True, f"Successfully set game path to: {path}")
