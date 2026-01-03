"""
Home Screen - Installed Mods List

Shows all installed mods with options to enable, disable, and uninstall.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static, DataTable, Input
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive

from typing import List, Optional
from app.models.mod import Mod


class HomeScreen(Screen):
    """Main screen showing installed mods"""
    
    BINDINGS = [
        Binding("e", "toggle_mod", "Enable/Disable"),
        Binding("u", "uninstall_mod", "Uninstall"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "view_details", "Details"),
        Binding("/", "focus_search", "Search"),
        Binding("escape", "clear_search", "Clear"),
    ]
    
    # Reactive state
    mods: reactive[List[Mod]] = reactive(list)
    selected_mod_id: reactive[Optional[int]] = reactive(None)
    search_query: reactive[str] = reactive("")
    
    def compose(self) -> ComposeResult:
        """Create the home screen layout"""
        yield Container(
            Horizontal(
                Static("Installed Mods", id="title", classes="screen-title"),
                Input(placeholder="Search mods...", id="search-input"),
                id="header-bar"
            ),
            DataTable(id="mod-table"),
            Static("", id="status-bar"),
            id="home-container"
        )
        yield Footer()
    
    async def on_mount(self) -> None:
        """Initialize the screen"""
        table = self.query_one("#mod-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        
        # Add columns
        table.add_columns(
            "Status",
            "Name",
            "Version", 
            "Type",
            "Size",
        )
        
        # Load mods
        await self.action_refresh()
    
    async def action_refresh(self) -> None:
        """Refresh the mod list"""
        app = self.app
        if app.service:
            try:
                self.mods = await app.service.get_installed_mods()
                self._update_table()
                self.notify(f"Loaded {len(self.mods)} mods")
            except Exception as e:
                self.notify(f"Failed to load mods: {e}", severity="error")
    
    def _update_table(self) -> None:
        """Update the table with current mods"""
        table = self.query_one("#mod-table", DataTable)
        table.clear()
        
        query = self.search_query.lower()
        
        for mod in self.mods:
            # Filter by search
            if query and query not in mod.name.lower():
                continue
            
            # Status indicator
            status = "[green]●[/]" if mod.is_enabled else "[dim]○[/]"
            
            # Format size
            size = self._format_size(mod.file_size) if mod.file_size else "-"
            
            table.add_row(
                status,
                mod.name,
                mod.version or "-",
                mod.mod_type or "unknown",
                size,
                key=str(mod.id)
            )
    
    def _format_size(self, size: int) -> str:
        """Format file size in human-readable form"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        if event.input.id == "search-input":
            self.search_query = event.value
            self._update_table()
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection"""
        if event.row_key:
            self.selected_mod_id = int(event.row_key.value)
    
    async def action_toggle_mod(self) -> None:
        """Toggle the selected mod's enabled state"""
        if self.selected_mod_id is None:
            self.notify("No mod selected", severity="warning")
            return
        
        app = self.app
        if app.service:
            try:
                await app.service.toggle_mod(self.selected_mod_id)
                await self.action_refresh()
                self.notify("Mod toggled")
            except Exception as e:
                self.notify(f"Failed to toggle mod: {e}", severity="error")
    
    async def action_uninstall_mod(self) -> None:
        """Uninstall the selected mod"""
        if self.selected_mod_id is None:
            self.notify("No mod selected", severity="warning")
            return
        
        # Find mod name for confirmation
        mod = next((m for m in self.mods if m.id == self.selected_mod_id), None)
        if not mod:
            return
        
        # Show confirmation dialog (or auto-confirm in non-interactive mode)
        from app.tui.screens.dialogs import ConfirmDialog
        
        async def on_confirm(confirmed: bool) -> None:
            if confirmed:
                app = self.app
                if app.service:
                    try:
                        await app.service.uninstall_mod(self.selected_mod_id)
                        await self.action_refresh()
                        self.notify(f"Uninstalled {mod.name}")
                    except Exception as e:
                        self.notify(f"Failed to uninstall: {e}", severity="error")
        
        # Check for non-interactive mode
        app = self.app
        auto_confirm = getattr(app, 'auto_confirm', False) and getattr(app, 'non_interactive', False)
        
        self.app.push_screen(
            ConfirmDialog(
                f"Uninstall '{mod.name}'?",
                auto_confirm=auto_confirm
            ),
            on_confirm
        )
    
    async def action_view_details(self) -> None:
        """View details for the selected mod"""
        if self.selected_mod_id is None:
            self.notify("No mod selected", severity="warning")
            return
        
        from app.tui.screens.mod_detail import ModDetailScreen
        self.app.push_screen(ModDetailScreen(self.selected_mod_id))
    
    def action_focus_search(self) -> None:
        """Focus the search input"""
        self.query_one("#search-input", Input).focus()
    
    def action_clear_search(self) -> None:
        """Clear search and return focus to table"""
        search = self.query_one("#search-input", Input)
        search.value = ""
        self.search_query = ""
        self._update_table()
        self.query_one("#mod-table", DataTable).focus()
