"""
Help Screen - Keyboard shortcuts and usage information
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button
from textual.containers import Container, VerticalScroll
from textual.binding import Binding


class HelpScreen(ModalScreen):
    """Help and keyboard shortcuts screen"""
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("?", "close", "Close"),
    ]
    
    HELP_TEXT = """
[bold cyan]Cyberpunk 2077 Mod Manager for macOS[/]

[bold]Global Shortcuts[/]
  [magenta]h[/]  →  Home (installed mods)
  [magenta]b[/]  →  Browse Nexus Mods
  [magenta]i[/]  →  Install new mod
  [magenta]s[/]  →  Settings
  [magenta]q[/]  →  Quit
  [magenta]?[/]  →  This help screen
  [magenta]Ctrl+D[/]  →  Toggle dark mode

[bold]Home Screen[/]
  [magenta]e[/]  →  Enable/disable selected mod
  [magenta]u[/]  →  Uninstall selected mod
  [magenta]r[/]  →  Refresh mod list
  [magenta]Enter[/]  →  View mod details
  [magenta]/[/]  →  Focus search
  [magenta]Escape[/]  →  Clear search

[bold]Browse Screen[/]
  [magenta]/[/]  →  Focus search
  [magenta]Enter[/]  →  Install selected mod
  [magenta]n[/]  →  Next page
  [magenta]p[/]  →  Previous page
  [magenta]r[/]  →  Refresh search

[bold]Install Screen[/]
  [magenta]f[/]  →  Pick file
  [magenta]Escape[/]  →  Cancel installation

[bold]FOMOD Wizard[/]
  [magenta]←[/]  →  Previous step
  [magenta]→[/]  →  Next step
  [magenta]Enter[/]  →  Continue
  [magenta]Escape[/]  →  Cancel

[bold]Navigation[/]
  [magenta]Tab[/]  →  Next widget
  [magenta]Shift+Tab[/]  →  Previous widget
  [magenta]Arrow keys[/]  →  Navigate within widgets

[bold]About[/]
This mod manager is designed specifically for running
Cyberpunk 2077 mods on macOS via CrossOver/Whiskey.

For more information, visit the project documentation.
"""
    
    def compose(self) -> ComposeResult:
        yield Container(
            VerticalScroll(
                Static(self.HELP_TEXT, id="help-text"),
                id="help-scroll"
            ),
            Button("Close", id="close-btn", variant="primary"),
            id="help-container"
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
    
    def action_close(self) -> None:
        self.dismiss()
