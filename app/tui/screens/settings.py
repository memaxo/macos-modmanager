"""
Settings Screen - Configuration

Manage game path, Nexus API key, and other settings.
"""

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Footer, Static, Button, Input, Label, Switch,
    Collapsible
)
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive


class SettingsScreen(Screen):
    """Application settings screen"""
    
    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("s", "save", "Save"),
    ]
    
    # Reactive state
    game_path: reactive[str] = reactive("")
    nexus_api_key: reactive[str] = reactive("")
    auto_backup: reactive[bool] = reactive(True)
    strict_compatibility: reactive[bool] = reactive(True)
    auto_remove_quarantine: reactive[bool] = reactive(True)
    has_changes: reactive[bool] = reactive(False)
    
    def compose(self) -> ComposeResult:
        """Create the settings layout"""
        yield Container(
            Static("Settings", id="title", classes="screen-title"),
            
            # Game Settings
            Collapsible(
                Container(
                    Label("Cyberpunk 2077 Installation Path:"),
                    Horizontal(
                        Input(placeholder="Path to game...", id="game-path-input"),
                        Button("Browse", id="browse-game-btn"),
                        Button("Detect", id="detect-game-btn", variant="primary"),
                        id="game-path-row"
                    ),
                    Static("", id="game-status"),
                    id="game-path-section"
                ),
                title="Game Configuration",
                collapsed=False
            ),
            
            # Nexus Settings
            Collapsible(
                Container(
                    Label("Nexus Mods API Key:"),
                    Horizontal(
                        Input(
                            placeholder="Enter your API key...",
                            password=True,
                            id="api-key-input"
                        ),
                        Button("Test", id="test-api-btn"),
                        id="api-key-row"
                    ),
                    Static(
                        "[dim]Get your API key from nexusmods.com/users/myaccount?tab=api[/]",
                        id="api-help"
                    ),
                    Static("", id="api-status"),
                    id="api-section"
                ),
                title="Nexus Mods Integration"
            ),
            
            # Installation Settings
            Collapsible(
                Container(
                    Horizontal(
                        Switch(value=True, id="backup-switch"),
                        Label("Create backups before installing"),
                        id="backup-row"
                    ),
                    Horizontal(
                        Switch(value=True, id="compat-switch"),
                        Label("Strict macOS compatibility checking"),
                        id="compat-row"
                    ),
                    Horizontal(
                        Switch(value=True, id="quarantine-switch"),
                        Label("Auto-remove macOS quarantine flags"),
                        id="quarantine-row"
                    ),
                    id="install-options"
                ),
                title="Installation Options"
            ),
            
            # Paths Info
            Collapsible(
                Container(
                    Static("", id="paths-info"),
                    id="paths-section"
                ),
                title="Data Directories"
            ),
            
            # Save button
            Horizontal(
                Button("Save Settings", id="save-btn", variant="primary"),
                Button("Reset to Defaults", id="reset-btn"),
                id="settings-actions"
            ),
            
            id="settings-container"
        )
        yield Footer()
    
    async def on_mount(self) -> None:
        """Load current settings"""
        await self._load_settings()
    
    async def _load_settings(self) -> None:
        """Load settings from config and database"""
        from app.config import settings
        
        # Game path
        if settings.custom_game_path:
            self.game_path = settings.custom_game_path
            self.query_one("#game-path-input", Input).value = settings.custom_game_path
        
        # Load from database via service
        app = self.app
        if app.service:
            try:
                db_settings = await app.service.get_settings()
                
                if db_settings.get("nexus_api_key"):
                    # Show masked key
                    self.query_one("#api-key-input", Input).value = "••••••••••••••••"
                    self.nexus_api_key = db_settings["nexus_api_key"]
                
                # Boolean settings
                self.auto_backup = db_settings.get("backup_before_install", True)
                self.strict_compatibility = db_settings.get("strict_compatibility", True)
                self.auto_remove_quarantine = db_settings.get("auto_remove_quarantine", True)
                
                # Update switches
                self.query_one("#backup-switch", Switch).value = self.auto_backup
                self.query_one("#compat-switch", Switch).value = self.strict_compatibility
                self.query_one("#quarantine-switch", Switch).value = self.auto_remove_quarantine
                
            except Exception as e:
                self.notify(f"Failed to load settings: {e}", severity="error")
        
        # Update paths info
        self._update_paths_info()
        
        self.has_changes = False
    
    def _update_paths_info(self) -> None:
        """Update the paths information display"""
        from app.config import settings
        
        info = f"""[bold]Staging Directory:[/]
{settings.staging_dir}

[bold]Backups Directory:[/]
{settings.backups_dir}

[bold]Cache Directory:[/]
{settings.cache_dir}

[bold]Database:[/]
{settings.database_url}"""
        
        self.query_one("#paths-info", Static).update(info)
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Track changes"""
        self.has_changes = True
        
        if event.input.id == "game-path-input":
            self.game_path = event.value
        elif event.input.id == "api-key-input":
            # Don't update if it's the masked value
            if event.value != "••••••••••••••••":
                self.nexus_api_key = event.value
    
    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Track switch changes"""
        self.has_changes = True
        
        if event.switch.id == "backup-switch":
            self.auto_backup = event.value
        elif event.switch.id == "compat-switch":
            self.strict_compatibility = event.value
        elif event.switch.id == "quarantine-switch":
            self.auto_remove_quarantine = event.value
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "browse-game-btn":
            await self._browse_game_path()
        elif event.button.id == "detect-game-btn":
            await self._detect_game_path()
        elif event.button.id == "test-api-btn":
            await self._test_api_key()
        elif event.button.id == "save-btn":
            await self.action_save()
        elif event.button.id == "reset-btn":
            await self._reset_defaults()
    
    async def _browse_game_path(self) -> None:
        """Open folder picker for game path"""
        from app.tui.screens.dialogs import FolderPickerDialog
        
        async def on_folder_selected(path: Optional[Path]) -> None:
            if path:
                self.query_one("#game-path-input", Input).value = str(path)
                self.game_path = str(path)
                await self._validate_game_path()
        
        # In non-interactive mode with a pre-filled path, validate directly
        app = self.app
        if getattr(app, 'non_interactive', False):
            current_path = self.query_one("#game-path-input", Input).value
            if current_path:
                await on_folder_selected(Path(current_path))
                return
        
        self.app.push_screen(
            FolderPickerDialog(title="Select Cyberpunk 2077 Installation"),
            on_folder_selected
        )
    
    async def _detect_game_path(self) -> None:
        """Auto-detect game installation"""
        from app.core.game_detector import detect_game_installations
        
        self.notify("Detecting game installation...")
        
        try:
            installations = await detect_game_installations()
            
            if installations:
                first = installations[0]
                self.query_one("#game-path-input", Input).value = first["path"]
                self.game_path = first["path"]
                
                self.query_one("#game-status", Static).update(
                    f"[green]✓ Found {first['launcher']} installation "
                    f"(v{first.get('version', 'unknown')})[/]"
                )
                self.has_changes = True
            else:
                self.query_one("#game-status", Static).update(
                    "[yellow]No installation found. Please set path manually.[/]"
                )
        except Exception as e:
            self.notify(f"Detection failed: {e}", severity="error")
    
    async def _validate_game_path(self) -> None:
        """Validate the game path"""
        path = Path(self.game_path)
        
        if not path.exists():
            self.query_one("#game-status", Static).update(
                "[red]✗ Path does not exist[/]"
            )
            return
        
        app_bundle = path / "Cyberpunk2077.app"
        if not app_bundle.exists():
            self.query_one("#game-status", Static).update(
                "[yellow]⚠ Cyberpunk2077.app not found in this directory[/]"
            )
        else:
            self.query_one("#game-status", Static).update(
                "[green]✓ Valid game installation[/]"
            )
    
    async def _test_api_key(self) -> None:
        """Test the Nexus API key"""
        api_key = self.query_one("#api-key-input", Input).value
        
        if api_key == "••••••••••••••••":
            api_key = self.nexus_api_key
        
        if not api_key or len(api_key) < 10:
            self.notify("Please enter an API key first", severity="warning")
            return
        
        self.notify("Testing API key...")
        
        try:
            app = self.app
            if app.service:
                is_valid = await app.service.test_nexus_api_key(api_key)
                
                if is_valid:
                    self.query_one("#api-status", Static).update(
                        "[green]✓ API key is valid[/]"
                    )
                else:
                    self.query_one("#api-status", Static).update(
                        "[red]✗ API key is invalid[/]"
                    )
        except Exception as e:
            self.query_one("#api-status", Static).update(
                f"[red]✗ Test failed: {e}[/]"
            )
    
    async def action_save(self) -> None:
        """Save all settings"""
        try:
            app = self.app
            if app.service:
                # Prepare settings
                settings_to_save = {
                    "custom_game_path": self.game_path if self.game_path else None,
                    "backup_before_install": self.auto_backup,
                    "strict_compatibility": self.strict_compatibility,
                    "auto_remove_quarantine": self.auto_remove_quarantine,
                }
                
                # Only save API key if it was changed
                api_key_input = self.query_one("#api-key-input", Input).value
                if api_key_input and api_key_input != "••••••••••••••••":
                    settings_to_save["nexus_api_key"] = api_key_input
                
                await app.service.save_settings(settings_to_save)
                
                self.has_changes = False
                self.notify("Settings saved!", severity="information")
                
        except Exception as e:
            self.notify(f"Failed to save settings: {e}", severity="error")
    
    async def _reset_defaults(self) -> None:
        """Reset to default settings"""
        self.query_one("#game-path-input", Input).value = ""
        self.query_one("#backup-switch", Switch).value = True
        self.query_one("#compat-switch", Switch).value = True
        self.query_one("#quarantine-switch", Switch).value = True
        
        self.game_path = ""
        self.auto_backup = True
        self.strict_compatibility = True
        self.auto_remove_quarantine = True
        self.has_changes = True
        
        self.notify("Settings reset to defaults")
    
    def action_go_back(self) -> None:
        """Go back to previous screen"""
        if self.has_changes:
            # Could show confirmation dialog here
            pass
        self.app.switch_mode("home")
