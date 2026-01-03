"""
Textual TUI for macOS Mod Manager

A terminal user interface for managing Cyberpunk 2077 mods on macOS.

Supports both interactive TUI mode and non-interactive CLI mode.

Environment Variables:
    MOD_MANAGER_NON_INTERACTIVE: Set to "1" to enable non-interactive mode
    MOD_MANAGER_YES: Set to "1" to auto-confirm all prompts  
    MOD_MANAGER_GAME_PATH: Override game path

CLI Usage:
    # Interactive TUI
    mod-manager-tui
    
    # Non-interactive CLI commands
    mod-manager list                           # List installed mods
    mod-manager install ./mod.zip --yes        # Install with auto-confirm
    mod-manager enable 1                       # Enable mod by ID
    mod-manager disable "Mod Name"             # Disable mod by name
    mod-manager uninstall 1 --yes              # Uninstall with auto-confirm
    mod-manager config set-game-path /path     # Configure game path
    mod-manager backup create --name "pre-update"  # Create backup
    
    # JSON output for scripting
    mod-manager list --json
    mod-manager info 1 --json
"""

from app.tui.app import (
    ModManagerApp,
    is_non_interactive,
    should_auto_confirm,
    get_env_game_path,
)
from app.tui.cli import NonInteractiveCLI

__all__ = [
    "ModManagerApp",
    "NonInteractiveCLI",
    "is_non_interactive",
    "should_auto_confirm",
    "get_env_game_path",
]
