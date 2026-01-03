"""
Mod Table Widget - Reusable DataTable for displaying mods
"""

from typing import List, Optional, Callable, Any

from textual.widgets import DataTable
from textual.reactive import reactive

from app.models.mod import Mod


class ModTable(DataTable):
    """Enhanced DataTable for displaying mod information"""
    
    # Custom columns configuration
    DEFAULT_COLUMNS = [
        ("status", "Status", 6),
        ("name", "Name", None),  # None = auto-width
        ("version", "Version", 10),
        ("type", "Type", 12),
        ("size", "Size", 10),
    ]
    
    # Reactive state
    selected_mod_id: reactive[Optional[int]] = reactive(None)
    filter_text: reactive[str] = reactive("")
    filter_type: reactive[Optional[str]] = reactive(None)
    filter_enabled: reactive[Optional[bool]] = reactive(None)
    
    def __init__(
        self,
        columns: Optional[List[tuple]] = None,
        on_select: Optional[Callable[[int], None]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.columns_config = columns or self.DEFAULT_COLUMNS
        self.on_select_callback = on_select
        self._mods: List[Mod] = []
        
        self.cursor_type = "row"
        self.zebra_stripes = True
    
    def on_mount(self) -> None:
        """Set up columns on mount"""
        for col_id, col_name, width in self.columns_config:
            if width:
                self.add_column(col_name, key=col_id, width=width)
            else:
                self.add_column(col_name, key=col_id)
    
    def set_mods(self, mods: List[Mod]) -> None:
        """Set the mods to display"""
        self._mods = mods
        self._refresh_table()
    
    def _refresh_table(self) -> None:
        """Refresh table with current filters"""
        self.clear()
        
        for mod in self._mods:
            # Apply filters
            if not self._passes_filter(mod):
                continue
            
            row_data = self._format_row(mod)
            self.add_row(*row_data, key=str(mod.id))
    
    def _passes_filter(self, mod: Mod) -> bool:
        """Check if mod passes current filters"""
        # Text filter
        if self.filter_text:
            search = self.filter_text.lower()
            if search not in mod.name.lower():
                if not mod.author or search not in mod.author.lower():
                    return False
        
        # Type filter
        if self.filter_type:
            if mod.mod_type != self.filter_type:
                return False
        
        # Enabled filter
        if self.filter_enabled is not None:
            if mod.is_enabled != self.filter_enabled:
                return False
        
        return True
    
    def _format_row(self, mod: Mod) -> tuple:
        """Format a mod as a table row"""
        status = "[green]●[/]" if mod.is_enabled else "[dim]○[/]"
        version = mod.version or "-"
        mod_type = mod.mod_type or "unknown"
        size = self._format_size(mod.file_size)
        
        return (status, mod.name, version, mod_type, size)
    
    def _format_size(self, size: Optional[int]) -> str:
        """Format file size in human-readable form"""
        if size is None:
            return "-"
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def watch_filter_text(self, value: str) -> None:
        """React to filter text changes"""
        self._refresh_table()
    
    def watch_filter_type(self, value: Optional[str]) -> None:
        """React to type filter changes"""
        self._refresh_table()
    
    def watch_filter_enabled(self, value: Optional[bool]) -> None:
        """React to enabled filter changes"""
        self._refresh_table()
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection"""
        if event.row_key:
            mod_id = int(event.row_key.value)
            self.selected_mod_id = mod_id
            if self.on_select_callback:
                self.on_select_callback(mod_id)
    
    def get_selected_mod(self) -> Optional[Mod]:
        """Get the currently selected mod"""
        if self.selected_mod_id is None:
            return None
        return next((m for m in self._mods if m.id == self.selected_mod_id), None)
    
    def clear_filters(self) -> None:
        """Clear all filters"""
        self.filter_text = ""
        self.filter_type = None
        self.filter_enabled = None
