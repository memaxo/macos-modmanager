"""
Install Screen - Mod Installation

Handles local file installation and Nexus Mods downloads with progress tracking.
"""

from pathlib import Path
from typing import Optional, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Footer, Static, Button, Input, ProgressBar, 
    Label, LoadingIndicator, RichLog
)
from textual.containers import Container, Horizontal, Vertical, Center
from textual.reactive import reactive
from textual import work
from textual.worker import Worker, get_current_worker


class InstallScreen(Screen):
    """Mod installation screen with progress tracking"""
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("f", "pick_file", "Pick File"),
    ]
    
    # Reactive state
    install_stage: reactive[str] = reactive("idle")
    install_progress: reactive[int] = reactive(0)
    install_message: reactive[str] = reactive("")
    is_installing: reactive[bool] = reactive(False)
    
    def __init__(
        self,
        nexus_mod_id: Optional[int] = None,
        mod_name: Optional[str] = None,
        local_file: Optional[Path] = None,
        name: str = "install"
    ):
        super().__init__(name=name)
        self.nexus_mod_id = nexus_mod_id
        self.mod_name = mod_name or "Unknown Mod"
        self.local_file = local_file
        self._current_worker: Optional[Worker] = None
    
    def compose(self) -> ComposeResult:
        """Create the install screen layout"""
        yield Container(
            Static("Install Mod", id="title", classes="screen-title"),
            
            # File input section
            Container(
                Label("Install from local file:"),
                Horizontal(
                    Input(
                        placeholder="Path to mod archive (.zip, .7z, .rar)...",
                        id="file-path-input"
                    ),
                    Button("Browse", id="browse-btn"),
                    id="file-input-row"
                ),
                id="file-section"
            ),
            
            # OR divider
            Center(
                Static("─── OR ───", classes="divider"),
            ),
            
            # Nexus input section
            Container(
                Label("Install from Nexus Mods:"),
                Horizontal(
                    Input(
                        placeholder="Enter Nexus Mod ID (e.g., 12345)...",
                        id="nexus-id-input"
                    ),
                    Button("Install", id="nexus-install-btn", variant="primary"),
                    id="nexus-input-row"
                ),
                id="nexus-section"
            ),
            
            # Progress section (hidden initially)
            Container(
                Static("", id="install-title"),
                ProgressBar(id="progress-bar", total=100),
                Static("", id="stage-label"),
                Static("", id="message-label"),
                RichLog(id="install-log", highlight=True, markup=True),
                Horizontal(
                    Button("Cancel", id="cancel-btn", variant="error"),
                    id="progress-actions"
                ),
                id="progress-section"
            ),
            
            id="install-container"
        )
        yield Footer()
    
    async def on_mount(self) -> None:
        """Initialize the screen"""
        # Hide progress section initially
        self.query_one("#progress-section").display = False
        
        # Pre-fill if launched with mod info
        if self.nexus_mod_id:
            self.query_one("#nexus-id-input", Input).value = str(self.nexus_mod_id)
            self.query_one("#install-title", Static).update(f"Installing: {self.mod_name}")
        
        if self.local_file:
            self.query_one("#file-path-input", Input).value = str(self.local_file)
    
    def watch_install_progress(self, progress: int) -> None:
        """Update progress bar"""
        bar = self.query_one("#progress-bar", ProgressBar)
        bar.update(progress=progress)
    
    def watch_install_stage(self, stage: str) -> None:
        """Update stage label"""
        self.query_one("#stage-label", Static).update(f"[bold]{stage}[/]")
    
    def watch_install_message(self, message: str) -> None:
        """Update message label"""
        self.query_one("#message-label", Static).update(message)
    
    def watch_is_installing(self, is_installing: bool) -> None:
        """Toggle UI sections based on install state"""
        self.query_one("#file-section").display = not is_installing
        self.query_one("#nexus-section").display = not is_installing
        self.query_one("#progress-section").display = is_installing
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "browse-btn":
            await self.action_pick_file()
        elif event.button.id == "nexus-install-btn":
            await self._start_nexus_install()
        elif event.button.id == "cancel-btn":
            await self.action_cancel()
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission"""
        if event.input.id == "file-path-input":
            path = Path(event.value)
            if path.exists() and path.is_file():
                await self._start_local_install(path)
            else:
                self.notify("File not found", severity="error")
        elif event.input.id == "nexus-id-input":
            await self._start_nexus_install()
    
    async def action_pick_file(self) -> None:
        """Open file picker dialog"""
        from app.tui.screens.dialogs import FilePickerDialog
        
        async def on_file_selected(path: Optional[Path]) -> None:
            if path:
                self.query_one("#file-path-input", Input).value = str(path)
                await self._start_local_install(path)
        
        # In non-interactive mode with a pre-filled path, use that directly
        app = self.app
        if getattr(app, 'non_interactive', False):
            current_path = self.query_one("#file-path-input", Input).value
            if current_path:
                path = Path(current_path)
                if path.exists():
                    await on_file_selected(path)
                    return
        
        self.app.push_screen(
            FilePickerDialog(
                title="Select Mod Archive",
                extensions=[".zip", ".7z", ".rar"]
            ),
            on_file_selected
        )
    
    async def _start_local_install(self, file_path: Path) -> None:
        """Start installation from local file"""
        if self.is_installing:
            self.notify("Installation already in progress", severity="warning")
            return
        
        self.is_installing = True
        self.install_stage = "Starting..."
        self.install_progress = 0
        
        log = self.query_one("#install-log", RichLog)
        log.clear()
        log.write(f"[cyan]Installing from: {file_path}[/]")
        
        self._install_local_file(file_path)
    
    @work(exclusive=True, thread=True)
    def _install_local_file(self, file_path: Path) -> None:
        """Background worker for local file installation"""
        worker = get_current_worker()
        log = self.query_one("#install-log", RichLog)
        
        def progress_callback(stage: str, percent: int, message: str):
            if not worker.is_cancelled:
                self.call_from_thread(self._update_progress, stage, percent, message)
        
        try:
            app = self.app
            if app.service:
                # Run async install in thread
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    mod = loop.run_until_complete(
                        app.service.install_local_mod(
                            file_path,
                            progress_callback=progress_callback
                        )
                    )
                    
                    if not worker.is_cancelled:
                        self.call_from_thread(
                            self._on_install_complete,
                            mod.name if mod else "Unknown"
                        )
                except Exception as e:
                    if not worker.is_cancelled:
                        self.call_from_thread(self._on_install_error, str(e))
                finally:
                    loop.close()
        except Exception as e:
            if not worker.is_cancelled:
                self.call_from_thread(self._on_install_error, str(e))
    
    async def _start_nexus_install(self) -> None:
        """Start installation from Nexus Mods"""
        mod_id_str = self.query_one("#nexus-id-input", Input).value.strip()
        
        try:
            mod_id = int(mod_id_str)
        except ValueError:
            self.notify("Invalid mod ID", severity="error")
            return
        
        if self.is_installing:
            self.notify("Installation already in progress", severity="warning")
            return
        
        self.is_installing = True
        self.nexus_mod_id = mod_id
        self.install_stage = "Downloading..."
        self.install_progress = 0
        
        log = self.query_one("#install-log", RichLog)
        log.clear()
        log.write(f"[cyan]Downloading mod {mod_id} from Nexus...[/]")
        
        self._install_from_nexus(mod_id)
    
    @work(exclusive=True, thread=True)
    def _install_from_nexus(self, mod_id: int) -> None:
        """Background worker for Nexus installation"""
        worker = get_current_worker()
        
        def progress_callback(stage: str, percent: int, message: str):
            if not worker.is_cancelled:
                self.call_from_thread(self._update_progress, stage, percent, message)
        
        try:
            app = self.app
            if app.service:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    mod = loop.run_until_complete(
                        app.service.install_from_nexus(
                            mod_id,
                            progress_callback=progress_callback
                        )
                    )
                    
                    if not worker.is_cancelled:
                        self.call_from_thread(
                            self._on_install_complete,
                            mod.name if mod else "Unknown"
                        )
                except Exception as e:
                    error_msg = str(e)
                    
                    # Check for FOMOD requirement
                    if "FOMOD" in error_msg or "FomodInstallRequired" in error_msg:
                        if not worker.is_cancelled:
                            self.call_from_thread(self._on_fomod_required, mod_id)
                    else:
                        if not worker.is_cancelled:
                            self.call_from_thread(self._on_install_error, error_msg)
                finally:
                    loop.close()
        except Exception as e:
            if not worker.is_cancelled:
                self.call_from_thread(self._on_install_error, str(e))
    
    def _update_progress(self, stage: str, percent: int, message: str) -> None:
        """Update progress from worker thread"""
        self.install_stage = stage
        self.install_progress = percent
        self.install_message = message
        
        log = self.query_one("#install-log", RichLog)
        log.write(f"[{percent:3d}%] {stage}: {message}")
    
    def _on_install_complete(self, mod_name: str) -> None:
        """Handle successful installation"""
        self.is_installing = False
        self.install_stage = "Complete!"
        self.install_progress = 100
        self.install_message = f"Successfully installed {mod_name}"
        
        log = self.query_one("#install-log", RichLog)
        log.write(f"[green]✓ Installation complete: {mod_name}[/]")
        
        self.notify(f"Installed {mod_name}", severity="information")
    
    def _on_install_error(self, error: str) -> None:
        """Handle installation error"""
        self.is_installing = False
        self.install_stage = "Failed"
        self.install_message = error
        
        log = self.query_one("#install-log", RichLog)
        log.write(f"[red]✗ Installation failed: {error}[/]")
        
        self.notify(f"Installation failed: {error}", severity="error")
    
    def _on_fomod_required(self, mod_id: int) -> None:
        """Handle FOMOD installer requirement"""
        self.is_installing = False
        
        log = self.query_one("#install-log", RichLog)
        log.write("[yellow]This mod requires FOMOD wizard configuration[/]")
        
        # Launch FOMOD wizard
        from app.tui.screens.fomod_wizard import FomodWizardScreen
        self.app.push_screen(FomodWizardScreen(nexus_mod_id=mod_id))
    
    async def action_cancel(self) -> None:
        """Cancel current installation"""
        if self._current_worker:
            self._current_worker.cancel()
        
        self.is_installing = False
        self.install_stage = "Cancelled"
        self.notify("Installation cancelled")
