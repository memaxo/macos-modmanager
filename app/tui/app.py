"""
Main TUI Application for macOS Mod Manager

A Textual-based terminal user interface for managing Cyberpunk 2077 mods.

Supports both interactive TUI mode and non-interactive CLI mode.
Environment variables:
    MOD_MANAGER_NON_INTERACTIVE: Set to "1" to enable non-interactive mode
    MOD_MANAGER_YES: Set to "1" to auto-confirm all prompts
    MOD_MANAGER_GAME_PATH: Override game path
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from app.config import settings
from app.core.game_detector import get_primary_game_path


def is_non_interactive() -> bool:
    """Check if running in non-interactive mode."""
    return os.environ.get("MOD_MANAGER_NON_INTERACTIVE", "").lower() in ("1", "true", "yes")


def should_auto_confirm() -> bool:
    """Check if prompts should be auto-confirmed."""
    return os.environ.get("MOD_MANAGER_YES", "").lower() in ("1", "true", "yes")


def get_env_game_path() -> Optional[Path]:
    """Get game path from environment variable."""
    path = os.environ.get("MOD_MANAGER_GAME_PATH")
    if path:
        return Path(path)
    return None


class ModManagerApp(App):
    """Main TUI application for mod management
    
    Supports non-interactive mode via MOD_MANAGER_NON_INTERACTIVE=1 environment variable.
    When in non-interactive mode, dialogs auto-confirm based on MOD_MANAGER_YES setting.
    """
    
    CSS_PATH = "styles/app.tcss"
    TITLE = "Cyberpunk 2077 Mod Manager"
    SUB_TITLE = "macOS Edition"
    
    BINDINGS = [
        Binding("h", "switch_mode('home')", "Home", priority=True),
        Binding("b", "switch_mode('browse')", "Browse"),
        Binding("i", "switch_mode('install')", "Install"),
        Binding("s", "switch_mode('settings')", "Settings"),
        Binding("q", "quit", "Quit", priority=True),
        Binding("?", "show_help", "Help"),
        Binding("ctrl+d", "toggle_dark", "Toggle Dark"),
    ]
    
    # Screens are set up after imports are ready
    MODES: dict = {}
    
    def __init__(
        self,
        game_path: Optional[Path] = None,
        non_interactive: bool = False,
        auto_confirm: bool = False
    ):
        super().__init__()
        # Priority: argument > environment > None
        self._game_path = game_path or get_env_game_path()
        self._db_session = None
        self._service = None
        # Non-interactive settings
        self.non_interactive = non_interactive or is_non_interactive()
        self.auto_confirm = auto_confirm or should_auto_confirm()
    
    @property
    def should_confirm(self) -> bool:
        """Check if confirmations should be shown."""
        return not (self.non_interactive and self.auto_confirm)
    
    @property
    def game_path(self) -> Optional[Path]:
        return self._game_path
    
    @property
    def service(self):
        return self._service
    
    async def on_mount(self) -> None:
        """Initialize the app on mount"""
        # Import screens here to avoid circular imports
        from app.tui.screens.home import HomeScreen
        from app.tui.screens.browse import BrowseScreen
        from app.tui.screens.install import InstallScreen
        from app.tui.screens.settings import SettingsScreen
        
        # Set up modes
        self.MODES = {
            "home": HomeScreen,
            "browse": BrowseScreen,
            "install": InstallScreen,
            "settings": SettingsScreen,
        }
        
        # Try to detect game path if not provided
        if self._game_path is None:
            self._game_path = await get_primary_game_path()
        
        if self._game_path is None:
            self.notify(
                "Game not found! Configure path in Settings.",
                severity="warning",
                timeout=5
            )
        
        # Initialize service
        from app.tui.services.tui_service import TUIModService
        self._service = TUIModService(self._game_path)
        
        # Start on home screen
        self.switch_mode("home")
    
    def action_switch_mode(self, mode: str) -> None:
        """Switch to a different screen mode"""
        if mode in self.MODES:
            # Install the screen if not already installed
            screen_class = self.MODES[mode]
            if mode not in self.screen_stack:
                self.install_screen(screen_class(), name=mode)
            self.switch_screen(mode)
        else:
            self.notify(f"Unknown mode: {mode}", severity="error")
    
    def action_toggle_dark(self) -> None:
        """Toggle between dark and light themes"""
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )
    
    def action_show_help(self) -> None:
        """Show help dialog"""
        from app.tui.screens.help import HelpScreen
        self.push_screen(HelpScreen())
    
    def compose(self) -> ComposeResult:
        """Compose the initial UI"""
        yield Header(show_clock=True)
        yield Footer()


def main():
    """Entry point for the TUI application"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cyberpunk 2077 Mod Manager TUI")
    parser.add_argument(
        "--game-path",
        type=Path,
        help="Path to Cyberpunk 2077 installation"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )
    
    args = parser.parse_args()
    
    app = ModManagerApp(game_path=args.game_path)
    app.run()


def cli_main():
    """Entry point for the non-interactive CLI"""
    from app.tui.cli import main as cli_entry
    cli_entry()


if __name__ == "__main__":
    main()
