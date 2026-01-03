"""
Search Bar Widget - Reusable search input with type filter
"""

from typing import Optional, List, Callable

from textual.app import ComposeResult
from textual.widgets import Static, Input, Select, Button
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.message import Message


class SearchBar(Container):
    """Search bar with optional type filter"""
    
    class SearchChanged(Message):
        """Message sent when search text changes"""
        def __init__(self, query: str):
            super().__init__()
            self.query = query
    
    class FilterChanged(Message):
        """Message sent when filter changes"""
        def __init__(self, filter_type: Optional[str]):
            super().__init__()
            self.filter_type = filter_type
    
    # Reactive state
    query: reactive[str] = reactive("")
    filter_type: reactive[Optional[str]] = reactive(None)
    
    # Default filter options
    DEFAULT_FILTERS = [
        ("All Types", None),
        ("Redscript", "redscript"),
        ("RED4ext", "red4ext"),
        ("TweakXL", "tweakxl"),
        ("ArchiveXL", "archivexl"),
        ("Archive", "archive"),
        ("CET", "cet"),
    ]
    
    def __init__(
        self,
        placeholder: str = "Search...",
        show_filter: bool = True,
        filter_options: Optional[List[tuple]] = None,
        on_search: Optional[Callable[[str], None]] = None,
        on_filter: Optional[Callable[[Optional[str]], None]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.placeholder_text = placeholder
        self.show_filter = show_filter
        self.filter_options = filter_options or self.DEFAULT_FILTERS
        self.on_search_callback = on_search
        self.on_filter_callback = on_filter
    
    def compose(self) -> ComposeResult:
        with Horizontal(id="search-bar-inner"):
            yield Input(
                placeholder=self.placeholder_text,
                id="search-input"
            )
            if self.show_filter:
                yield Select(
                    [(label, value) for label, value in self.filter_options],
                    id="type-filter",
                    prompt="Type",
                    allow_blank=True
                )
            yield Button("×", id="clear-btn", variant="default")
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        if event.input.id == "search-input":
            self.query = event.value
            self.post_message(self.SearchChanged(event.value))
            if self.on_search_callback:
                self.on_search_callback(event.value)
    
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle filter selection"""
        if event.select.id == "type-filter":
            self.filter_type = event.value
            self.post_message(self.FilterChanged(event.value))
            if self.on_filter_callback:
                self.on_filter_callback(event.value)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle clear button"""
        if event.button.id == "clear-btn":
            self.clear()
    
    def clear(self) -> None:
        """Clear search and filter"""
        self.query_one("#search-input", Input).value = ""
        if self.show_filter:
            self.query_one("#type-filter", Select).value = Select.BLANK
        self.query = ""
        self.filter_type = None
        self.post_message(self.SearchChanged(""))
        self.post_message(self.FilterChanged(None))
    
    def focus_input(self) -> None:
        """Focus the search input"""
        self.query_one("#search-input", Input).focus()
