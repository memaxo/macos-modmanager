"""
File Picker Widget - Inline file selection widget
"""

from pathlib import Path
from typing import Optional, List, Callable

from textual.app import ComposeResult
from textual.widgets import Static, Input, Button, DirectoryTree
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.message import Message


class FilePicker(Container):
    """Inline file picker widget with directory tree"""
    
    class FileSelected(Message):
        """Message sent when a file is selected"""
        def __init__(self, path: Path):
            super().__init__()
            self.path = path
    
    # Reactive state
    selected_path: reactive[Optional[Path]] = reactive(None)
    current_dir: reactive[Path] = reactive(Path.home())
    expanded: reactive[bool] = reactive(False)
    
    def __init__(
        self,
        label: str = "Select File",
        placeholder: str = "Path to file...",
        extensions: Optional[List[str]] = None,
        start_path: Optional[Path] = None,
        on_select: Optional[Callable[[Path], None]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.label_text = label
        self.placeholder_text = placeholder
        self.extensions = extensions or []
        self.start_path = start_path or Path.home()
        self.current_dir = self.start_path
        self.on_select_callback = on_select
    
    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(self.label_text, id="picker-label"),
            Horizontal(
                Input(placeholder=self.placeholder_text, id="path-input"),
                Button("Browse", id="browse-btn"),
                id="input-row"
            ),
            Container(
                VerticalScroll(
                    DirectoryTree(str(self.start_path), id="file-tree"),
                    id="tree-scroll"
                ),
                Static("", id="file-info"),
                id="tree-container"
            ),
            id="file-picker-inner"
        )
    
    def on_mount(self) -> None:
        """Initialize widget"""
        # Hide tree initially
        self.query_one("#tree-container").display = False
        
        tree = self.query_one("#file-tree", DirectoryTree)
        tree.show_root = True
        tree.show_guides = True
    
    def watch_expanded(self, expanded: bool) -> None:
        """Toggle tree visibility"""
        self.query_one("#tree-container").display = expanded
    
    def watch_selected_path(self, path: Optional[Path]) -> None:
        """React to path selection"""
        if path:
            self.query_one("#path-input", Input).value = str(path)
            self.query_one("#file-info", Static).update(
                f"[green]Selected: {path.name} ({self._format_size(path.stat().st_size)})[/]"
            )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Toggle browse mode"""
        if event.button.id == "browse-btn":
            self.expanded = not self.expanded
            event.button.label = "Close" if self.expanded else "Browse"
    
    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        """Handle file selection from tree"""
        path = Path(event.path)
        
        # Check extension filter
        if self.extensions:
            if path.suffix.lower() not in [e.lower() for e in self.extensions]:
                self.query_one("#file-info", Static).update(
                    f"[yellow]Invalid type. Expected: {', '.join(self.extensions)}[/]"
                )
                return
        
        self.selected_path = path
        self.expanded = False
        self.query_one("#browse-btn", Button).label = "Browse"
        
        # Post message and call callback
        self.post_message(self.FileSelected(path))
        if self.on_select_callback:
            self.on_select_callback(path)
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle manual path input"""
        if event.input.id == "path-input":
            path = Path(event.value)
            if path.exists() and path.is_file():
                # Check extension
                if self.extensions:
                    if path.suffix.lower() not in [e.lower() for e in self.extensions]:
                        self.query_one("#file-info", Static).update(
                            f"[yellow]Invalid type. Expected: {', '.join(self.extensions)}[/]"
                        )
                        return
                
                self.selected_path = path
                self.post_message(self.FileSelected(path))
                if self.on_select_callback:
                    self.on_select_callback(path)
            else:
                self.query_one("#file-info", Static).update(
                    "[red]File not found[/]"
                )
    
    def _format_size(self, size: int) -> str:
        """Format file size"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def get_path(self) -> Optional[Path]:
        """Get the currently selected path"""
        return self.selected_path
    
    def set_path(self, path: Path) -> None:
        """Set the path programmatically"""
        self.query_one("#path-input", Input).value = str(path)
        if path.exists():
            self.selected_path = path
    
    def clear(self) -> None:
        """Clear the selection"""
        self.query_one("#path-input", Input).value = ""
        self.query_one("#file-info", Static).update("")
        self.selected_path = None
