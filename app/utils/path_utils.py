from pathlib import Path
import subprocess
import sys


def get_steam_install_path() -> Path:
    """Get Cyberpunk 2077 Steam installation path on macOS"""
    return Path.home() / "Library/Application Support/Steam/steamapps/common/Cyberpunk 2077"


def get_gog_install_path() -> Path:
    """Get Cyberpunk 2077 GOG installation path on macOS"""
    return Path("/Applications/Cyberpunk 2077")


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


def make_executable(path: Path) -> None:
    """Make file executable"""
    path.chmod(0o755)
