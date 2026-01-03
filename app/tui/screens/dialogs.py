"""
Dialog Screens - Modal dialogs for confirmations, file picking, etc.

All dialogs support non-interactive operation via auto_confirm/auto_select parameters.
"""

from pathlib import Path
from typing import Optional, List, Callable

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Static, Input, DirectoryTree, Label
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.binding import Binding


class ConfirmDialog(ModalScreen[bool]):
    """Confirmation dialog with Yes/No buttons
    
    Args:
        message: The confirmation message to display
        title: Dialog title
        yes_label: Label for the confirm button
        no_label: Label for the cancel button
        auto_confirm: If True, automatically confirms without user input
        auto_cancel: If True, automatically cancels without user input
    """
    
    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(
        self,
        message: str,
        title: str = "Confirm",
        yes_label: str = "Yes",
        no_label: str = "No",
        auto_confirm: bool = False,
        auto_cancel: bool = False
    ):
        super().__init__()
        self.message = message
        self.title_text = title
        self.yes_label = yes_label
        self.no_label = no_label
        self.auto_confirm = auto_confirm
        self.auto_cancel = auto_cancel
    
    async def on_mount(self) -> None:
        """Handle auto-confirm/cancel on mount"""
        if self.auto_confirm:
            self.dismiss(True)
        elif self.auto_cancel:
            self.dismiss(False)
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static(self.title_text, id="dialog-title"),
            Static(self.message, id="dialog-message"),
            Horizontal(
                Button(self.no_label, id="no-btn", variant="default"),
                Button(self.yes_label, id="yes-btn", variant="primary"),
                id="dialog-buttons"
            ),
            id="confirm-dialog"
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)
    
    def action_confirm(self) -> None:
        self.dismiss(True)
    
    def action_cancel(self) -> None:
        self.dismiss(False)


class FilePickerDialog(ModalScreen[Optional[Path]]):
    """File picker dialog
    
    Args:
        title: Dialog title
        start_path: Initial directory to show
        extensions: List of allowed file extensions (e.g., [".zip", ".7z"])
        auto_select: If provided, automatically selects this path without user input
        auto_cancel: If True, automatically cancels without user input
    """
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select", "Select"),
    ]
    
    def __init__(
        self,
        title: str = "Select File",
        start_path: Optional[Path] = None,
        extensions: Optional[List[str]] = None,
        auto_select: Optional[Path] = None,
        auto_cancel: bool = False
    ):
        super().__init__()
        self.title_text = title
        self.start_path = start_path or Path.home()
        self.extensions = extensions or []
        self.selected_path: Optional[Path] = None
        self.auto_select = auto_select
        self.auto_cancel = auto_cancel
    
    async def on_mount_auto(self) -> None:
        """Handle auto-select/cancel - called after regular on_mount"""
        if self.auto_cancel:
            self.dismiss(None)
        elif self.auto_select and self.auto_select.exists():
            self.dismiss(self.auto_select)
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static(self.title_text, id="dialog-title"),
            Input(
                placeholder="Enter path or browse below...",
                id="path-input"
            ),
            VerticalScroll(
                DirectoryTree(str(self.start_path), id="file-tree"),
                id="file-tree-container"
            ),
            Static("", id="selection-info"),
            Horizontal(
                Button("Cancel", id="cancel-btn"),
                Button("Select", id="select-btn", variant="primary"),
                id="dialog-buttons"
            ),
            id="file-picker-dialog"
        )
    
    async def on_mount(self) -> None:
        # Handle auto-select/cancel first
        if self.auto_cancel:
            self.dismiss(None)
            return
        elif self.auto_select and self.auto_select.exists():
            self.dismiss(self.auto_select)
            return
        
        tree = self.query_one("#file-tree", DirectoryTree)
        tree.show_root = True
        tree.show_guides = True
    
    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        """Handle file selection in tree"""
        path = Path(event.path)
        
        # Check extension filter
        if self.extensions:
            if path.suffix.lower() not in [e.lower() for e in self.extensions]:
                self.query_one("#selection-info", Static).update(
                    f"[yellow]Invalid file type. Expected: {', '.join(self.extensions)}[/]"
                )
                return
        
        self.selected_path = path
        self.query_one("#path-input", Input).value = str(path)
        self.query_one("#selection-info", Static).update(
            f"[green]Selected: {path.name}[/]"
        )
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "path-input":
            path = Path(event.value)
            if path.exists() and path.is_file():
                self.selected_path = path
                self.dismiss(self.selected_path)
            else:
                self.query_one("#selection-info", Static).update(
                    "[red]File not found[/]"
                )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-btn":
            self.action_select()
        else:
            self.dismiss(None)
    
    def action_select(self) -> None:
        if self.selected_path:
            self.dismiss(self.selected_path)
        else:
            # Try the input value
            path_str = self.query_one("#path-input", Input).value
            if path_str:
                path = Path(path_str)
                if path.exists() and path.is_file():
                    self.dismiss(path)
                else:
                    self.query_one("#selection-info", Static).update(
                        "[red]Invalid path[/]"
                    )
    
    def action_cancel(self) -> None:
        self.dismiss(None)


class FolderPickerDialog(ModalScreen[Optional[Path]]):
    """Folder picker dialog
    
    Args:
        title: Dialog title
        start_path: Initial directory to show
        auto_select: If provided, automatically selects this path without user input
        auto_cancel: If True, automatically cancels without user input
    """
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select", "Select"),
    ]
    
    def __init__(
        self,
        title: str = "Select Folder",
        start_path: Optional[Path] = None,
        auto_select: Optional[Path] = None,
        auto_cancel: bool = False
    ):
        super().__init__()
        self.title_text = title
        self.start_path = start_path or Path.home()
        self.selected_path: Optional[Path] = None
        self.auto_select = auto_select
        self.auto_cancel = auto_cancel
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static(self.title_text, id="dialog-title"),
            Input(
                placeholder="Enter path or browse below...",
                id="path-input"
            ),
            VerticalScroll(
                DirectoryTree(str(self.start_path), id="folder-tree"),
                id="folder-tree-container"
            ),
            Static("", id="selection-info"),
            Horizontal(
                Button("Cancel", id="cancel-btn"),
                Button("Select", id="select-btn", variant="primary"),
                id="dialog-buttons"
            ),
            id="folder-picker-dialog"
        )
    
    async def on_mount(self) -> None:
        # Handle auto-select/cancel first
        if self.auto_cancel:
            self.dismiss(None)
            return
        elif self.auto_select and self.auto_select.exists():
            self.dismiss(self.auto_select)
            return
        
        tree = self.query_one("#folder-tree", DirectoryTree)
        tree.show_root = True
        tree.show_guides = True
    
    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        """Handle directory selection"""
        self.selected_path = Path(event.path)
        self.query_one("#path-input", Input).value = str(event.path)
        self.query_one("#selection-info", Static).update(
            f"[green]Selected: {event.path}[/]"
        )
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "path-input":
            path = Path(event.value)
            if path.exists() and path.is_dir():
                self.selected_path = path
                self.dismiss(self.selected_path)
            else:
                self.query_one("#selection-info", Static).update(
                    "[red]Folder not found[/]"
                )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-btn":
            self.action_select()
        else:
            self.dismiss(None)
    
    def action_select(self) -> None:
        if self.selected_path:
            self.dismiss(self.selected_path)
        else:
            path_str = self.query_one("#path-input", Input).value
            if path_str:
                path = Path(path_str)
                if path.exists() and path.is_dir():
                    self.dismiss(path)
                else:
                    self.query_one("#selection-info", Static).update(
                        "[red]Invalid path[/]"
                    )
    
    def action_cancel(self) -> None:
        self.dismiss(None)


class ErrorDialog(ModalScreen):
    """Error display dialog"""
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close"),
    ]
    
    def __init__(
        self,
        error_message: str,
        error_code: Optional[str] = None,
        suggestion: Optional[str] = None,
        title: str = "Error"
    ):
        super().__init__()
        self.title_text = title
        self.error_message = error_message
        self.error_code = error_code
        self.suggestion = suggestion
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static(f"[red]{self.title_text}[/]", id="error-title"),
            Static(self.error_message, id="error-message"),
            Static(
                f"[dim]Error Code: {self.error_code}[/]" if self.error_code else "",
                id="error-code"
            ),
            Static(
                f"[cyan]Suggestion: {self.suggestion}[/]" if self.suggestion else "",
                id="error-suggestion"
            ),
            Horizontal(
                Button("Close", id="close-btn", variant="primary"),
                id="dialog-buttons"
            ),
            id="error-dialog"
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
    
    def action_close(self) -> None:
        self.dismiss()
