from pathlib import Path
import subprocess
import sys
from typing import Optional, List


def get_steam_install_path() -> Path:
    """Get Cyberpunk 2077 Steam installation path on macOS (primary location)"""
    return Path.home() / "Library/Application Support/Steam/steamapps/common/Cyberpunk 2077"


def get_gog_install_path() -> Path:
    """Get Cyberpunk 2077 GOG installation path on macOS (primary location)"""
    return Path("/Applications/Cyberpunk 2077")


def get_all_possible_game_paths() -> List[Path]:
    """
    Get all possible game installation paths for Cyberpunk 2077 on macOS.
    Returns a list of paths to check, in priority order.
    """
    paths = [
        # Steam primary location
        Path.home() / "Library/Application Support/Steam/steamapps/common/Cyberpunk 2077",
        # GOG primary location
        Path("/Applications/Cyberpunk 2077"),
        # Alternative GOG location (user's Applications folder)
        Path.home() / "Applications/Cyberpunk 2077",
        # Alternative Steam locations (external drives, common patterns)
        Path("/Volumes/Games/SteamLibrary/steamapps/common/Cyberpunk 2077"),
        Path("/Volumes/SteamLibrary/steamapps/common/Cyberpunk 2077"),
        # External drive common patterns
        Path("/Volumes/External/Steam/steamapps/common/Cyberpunk 2077"),
        Path("/Volumes/Games/Cyberpunk 2077"),
        # Heroic Game Launcher (for GOG games)
        Path.home() / "Games/Heroic/Cyberpunk 2077",
        # CrossOver/Wine locations
        Path.home() / "Library/Application Support/CrossOver/Bottles/Steam/drive_c/Program Files (x86)/Steam/steamapps/common/Cyberpunk 2077",
        Path.home() / "Library/Application Support/CrossOver/Bottles/GOG Galaxy/drive_c/GOG Games/Cyberpunk 2077",
    ]
    return paths


def find_game_installation(app_bundle_name: str = "Cyberpunk2077.app") -> Optional[Path]:
    """
    Search for game installation across all known paths.
    
    Args:
        app_bundle_name: The name of the app bundle to look for
        
    Returns:
        Path to game installation directory if found, None otherwise
    """
    for path in get_all_possible_game_paths():
        if path.exists() and (path / app_bundle_name).exists():
            return path
    return None


def validate_game_path(path: Path, app_bundle_name: str = "Cyberpunk2077.app") -> bool:
    """
    Validate that a path is a valid game installation.
    
    Args:
        path: Path to validate
        app_bundle_name: Expected app bundle name
        
    Returns:
        True if valid game installation, False otherwise
    """
    if not path.exists():
        return False
    
    app_path = path / app_bundle_name
    if not app_path.exists():
        return False
    
    # Optionally check for other expected files/directories
    expected_dirs = ["r6", "archive"]
    for dir_name in expected_dirs:
        if not (path / dir_name).exists():
            # Not a hard failure - game might be freshly installed
            pass
    
    return True


def remove_quarantine_flag(path: Path) -> bool:
    """Remove macOS quarantine attribute"""
    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(
            ["xattr", "-d", "com.apple.quarantine", str(path)],
            check=True,
            capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def remove_quarantine_recursive(path: Path) -> tuple[int, int]:
    """
    Remove macOS quarantine attribute recursively from a directory.
    
    Args:
        path: Directory or file path
        
    Returns:
        Tuple of (success_count, failure_count)
    """
    if sys.platform != "darwin":
        return (0, 0)
    
    success_count = 0
    failure_count = 0
    
    if path.is_file():
        if remove_quarantine_flag(path):
            success_count += 1
        else:
            failure_count += 1
    elif path.is_dir():
        for item in path.rglob("*"):
            if item.is_file():
                if remove_quarantine_flag(item):
                    success_count += 1
                else:
                    failure_count += 1
    
    return (success_count, failure_count)


def make_executable(path: Path) -> None:
    """Make file executable"""
    path.chmod(0o755)


def make_executable_recursive(path: Path, extensions: Optional[List[str]] = None) -> int:
    """
    Make files executable recursively.
    
    Args:
        path: Directory or file path
        extensions: List of extensions to make executable (e.g., ['.dylib', '.so'])
                   If None, makes all files executable
    
    Returns:
        Number of files made executable
    """
    count = 0
    
    if path.is_file():
        if extensions is None or path.suffix in extensions:
            make_executable(path)
            count += 1
    elif path.is_dir():
        for item in path.rglob("*"):
            if item.is_file():
                if extensions is None or item.suffix in extensions:
                    make_executable(item)
                    count += 1
    
    return count
