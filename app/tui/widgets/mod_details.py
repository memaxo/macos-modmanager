"""
Mod Details Widget - Side panel for displaying mod information
"""

from typing import Optional

from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Container, Vertical
from textual.reactive import reactive

from app.models.mod import Mod


class ModDetails(Container):
    """Widget for displaying mod details in a sidebar"""
    
    # Reactive state
    mod: reactive[Optional[Mod]] = reactive(None)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold]Mod Details[/]", id="details-header"),
            Container(
                Static("[dim]Select a mod to view details[/]", id="no-selection"),
                Container(
                    Static("", id="mod-name"),
                    Static("", id="mod-version"),
                    Static("", id="mod-type"),
                    Static("", id="mod-author"),
                    Static("", id="mod-status"),
                    Static("", id="mod-size"),
                    Static("", id="mod-installed"),
                    Static("", id="mod-description"),
                    id="details-content"
                ),
                id="details-inner"
            ),
            id="mod-details-container"
        )
    
    def on_mount(self) -> None:
        """Hide content initially"""
        self.query_one("#details-content").display = False
    
    def watch_mod(self, mod: Optional[Mod]) -> None:
        """Update display when mod changes"""
        no_selection = self.query_one("#no-selection")
        content = self.query_one("#details-content")
        
        if mod is None:
            no_selection.display = True
            content.display = False
        else:
            no_selection.display = False
            content.display = True
            self._populate(mod)
    
    def _populate(self, mod: Mod) -> None:
        """Populate the details panel"""
        self.query_one("#mod-name", Static).update(
            f"[bold cyan]{mod.name}[/]"
        )
        
        self.query_one("#mod-version", Static).update(
            f"[bold]Version:[/] {mod.version or 'Unknown'}"
        )
        
        self.query_one("#mod-type", Static).update(
            f"[bold]Type:[/] {self._format_type(mod.mod_type)}"
        )
        
        if mod.author:
            self.query_one("#mod-author", Static).update(
                f"[bold]Author:[/] {mod.author}"
            )
        else:
            self.query_one("#mod-author", Static).update("")
        
        status = "[green]Enabled[/]" if mod.is_enabled else "[dim]Disabled[/]"
        self.query_one("#mod-status", Static).update(
            f"[bold]Status:[/] {status}"
        )
        
        self.query_one("#mod-size", Static).update(
            f"[bold]Size:[/] {self._format_size(mod.file_size)}"
        )
        
        if mod.created_at:
            date_str = mod.created_at.strftime("%Y-%m-%d %H:%M")
            self.query_one("#mod-installed", Static).update(
                f"[bold]Installed:[/] {date_str}"
            )
        else:
            self.query_one("#mod-installed", Static).update("")
        
        if mod.description:
            desc = mod.description[:200]
            if len(mod.description) > 200:
                desc += "..."
            self.query_one("#mod-description", Static).update(
                f"\n{desc}"
            )
        else:
            self.query_one("#mod-description", Static).update("")
    
    def _format_type(self, mod_type: Optional[str]) -> str:
        """Format mod type for display"""
        type_map = {
            "redscript": "[red]Redscript[/]",
            "red4ext": "[magenta]RED4ext[/]",
            "tweakxl": "[blue]TweakXL[/]",
            "archivexl": "[yellow]ArchiveXL[/]",
            "archive": "[cyan]Archive[/]",
            "cet": "[green]CET[/]",
        }
        if mod_type:
            return type_map.get(mod_type.lower(), mod_type)
        return "Unknown"
    
    def _format_size(self, size: Optional[int]) -> str:
        """Format file size"""
        if size is None:
            return "Unknown"
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def clear(self) -> None:
        """Clear the details panel"""
        self.mod = None
