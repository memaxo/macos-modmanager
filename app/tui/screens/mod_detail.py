"""
Mod Detail Screen - Detailed view of a single mod
"""

from typing import Optional, List

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button, DataTable, Label
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.binding import Binding


class ModDetailScreen(ModalScreen):
    """Detailed mod information screen"""
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("e", "toggle", "Enable/Disable"),
        Binding("u", "uninstall", "Uninstall"),
    ]
    
    def __init__(self, mod_id: int):
        super().__init__()
        self.mod_id = mod_id
        self.mod = None
    
    def compose(self) -> ComposeResult:
        yield Container(
            # Header
            Horizontal(
                Static("", id="mod-title"),
                Static("", id="mod-status"),
                id="detail-header"
            ),
            
            VerticalScroll(
                # Basic info
                Container(
                    Static("[bold]Details[/]", classes="section-title"),
                    Static("", id="mod-info"),
                    id="info-section"
                ),
                
                # Installed files
                Container(
                    Static("[bold]Installed Files[/]", classes="section-title"),
                    DataTable(id="files-table"),
                    id="files-section"
                ),
                
                # Dependencies
                Container(
                    Static("[bold]Dependencies[/]", classes="section-title"),
                    Static("", id="dependencies-info"),
                    id="deps-section"
                ),
                
                id="detail-scroll"
            ),
            
            # Actions
            Horizontal(
                Button("Close", id="close-btn"),
                Button("Enable/Disable", id="toggle-btn", variant="primary"),
                Button("Uninstall", id="uninstall-btn", variant="error"),
                id="detail-actions"
            ),
            
            id="mod-detail-container"
        )
    
    async def on_mount(self) -> None:
        """Load mod details"""
        await self._load_mod()
    
    async def _load_mod(self) -> None:
        """Fetch mod details from service"""
        app = self.app
        if app.service:
            try:
                self.mod = await app.service.get_mod_details(self.mod_id)
                if self.mod:
                    self._populate_details()
                else:
                    self.notify("Mod not found", severity="error")
                    self.dismiss()
            except Exception as e:
                self.notify(f"Failed to load mod: {e}", severity="error")
                self.dismiss()
    
    def _populate_details(self) -> None:
        """Populate the screen with mod details"""
        if not self.mod:
            return
        
        # Title and status
        self.query_one("#mod-title", Static).update(
            f"[bold]{self.mod.name}[/]"
        )
        
        status = "[green]Enabled[/]" if self.mod.is_enabled else "[dim]Disabled[/]"
        self.query_one("#mod-status", Static).update(status)
        
        # Basic info
        info_lines = [
            f"[bold]Version:[/] {self.mod.version or 'Unknown'}",
            f"[bold]Type:[/] {self.mod.mod_type or 'Unknown'}",
            f"[bold]Size:[/] {self._format_size(self.mod.file_size)}",
            f"[bold]Installed:[/] {self.mod.created_at.strftime('%Y-%m-%d %H:%M') if self.mod.created_at else 'Unknown'}",
        ]
        
        if self.mod.author:
            info_lines.append(f"[bold]Author:[/] {self.mod.author}")
        
        if self.mod.description:
            info_lines.append(f"\n[bold]Description:[/]\n{self.mod.description[:500]}")
        
        if self.mod.nexus_mod_id:
            info_lines.append(f"\n[bold]Nexus Mod ID:[/] {self.mod.nexus_mod_id}")
        
        self.query_one("#mod-info", Static).update("\n".join(info_lines))
        
        # Files table
        files_table = self.query_one("#files-table", DataTable)
        files_table.add_columns("File", "Size", "Status")
        
        if hasattr(self.mod, 'files') and self.mod.files:
            for file_info in self.mod.files[:50]:  # Limit display
                files_table.add_row(
                    file_info.get("path", "Unknown")[-60:],  # Truncate long paths
                    self._format_size(file_info.get("size", 0)),
                    "[green]OK[/]" if file_info.get("deployed") else "[dim]Staged[/]"
                )
        else:
            files_table.add_row("[dim]No file information available[/]", "", "")
        
        # Dependencies
        deps_text = "[dim]No dependencies[/]"
        if hasattr(self.mod, 'dependencies') and self.mod.dependencies:
            deps_list = []
            for dep in self.mod.dependencies:
                dep_status = "[green]✓[/]" if dep.get("installed") else "[red]✗[/]"
                deps_list.append(f"  {dep_status} {dep.get('name', 'Unknown')}")
            deps_text = "\n".join(deps_list)
        
        self.query_one("#dependencies-info", Static).update(deps_text)
    
    def _format_size(self, size: Optional[int]) -> str:
        """Format file size"""
        if size is None:
            return "-"
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.action_close()
        elif event.button.id == "toggle-btn":
            await self.action_toggle()
        elif event.button.id == "uninstall-btn":
            await self.action_uninstall()
    
    def action_close(self) -> None:
        self.dismiss()
    
    async def action_toggle(self) -> None:
        """Toggle mod enabled state"""
        if self.mod:
            app = self.app
            if app.service:
                try:
                    await app.service.toggle_mod(self.mod_id)
                    await self._load_mod()
                    self.notify("Mod toggled")
                except Exception as e:
                    self.notify(f"Failed to toggle: {e}", severity="error")
    
    async def action_uninstall(self) -> None:
        """Uninstall the mod"""
        if not self.mod:
            return
        
        from app.tui.screens.dialogs import ConfirmDialog
        
        async def on_confirm(confirmed: bool) -> None:
            if confirmed:
                app = self.app
                if app.service:
                    try:
                        await app.service.uninstall_mod(self.mod_id)
                        self.notify(f"Uninstalled {self.mod.name}")
                        self.dismiss()
                    except Exception as e:
                        self.notify(f"Failed to uninstall: {e}", severity="error")
        
        # Check for non-interactive mode
        app = self.app
        auto_confirm = getattr(app, 'auto_confirm', False) and getattr(app, 'non_interactive', False)
        
        self.app.push_screen(
            ConfirmDialog(
                f"Uninstall '{self.mod.name}'?",
                auto_confirm=auto_confirm
            ),
            on_confirm
        )
