"""
Browse Screen - Nexus Mods Browser

Search and browse mods from Nexus Mods with compatibility indicators.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static, DataTable, Input, Button, LoadingIndicator
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual import work

from typing import List, Dict, Any, Optional


class BrowseScreen(Screen):
    """Nexus Mods browser screen"""
    
    BINDINGS = [
        Binding("enter", "install_selected", "Install"),
        Binding("/", "focus_search", "Search"),
        Binding("n", "next_page", "Next Page"),
        Binding("p", "prev_page", "Prev Page"),
        Binding("r", "refresh", "Refresh"),
    ]
    
    # Reactive state
    search_results: reactive[List[Dict[str, Any]]] = reactive(list)
    selected_mod: reactive[Optional[Dict[str, Any]]] = reactive(None)
    current_page: reactive[int] = reactive(1)
    is_loading: reactive[bool] = reactive(False)
    search_query: reactive[str] = reactive("")
    
    def compose(self) -> ComposeResult:
        """Create the browse screen layout"""
        yield Container(
            Horizontal(
                Static("Browse Nexus Mods", id="title", classes="screen-title"),
                Input(placeholder="Search Nexus Mods...", id="nexus-search"),
                Button("Search", id="search-btn", variant="primary"),
                id="search-bar"
            ),
            Container(
                LoadingIndicator(id="loading"),
                DataTable(id="results-table"),
                id="results-container"
            ),
            Horizontal(
                Button("← Prev", id="prev-btn"),
                Static("Page 1", id="page-indicator"),
                Button("Next →", id="next-btn"),
                id="pagination"
            ),
            Static("", id="mod-preview"),
            id="browse-container"
        )
        yield Footer()
    
    async def on_mount(self) -> None:
        """Initialize the browse screen"""
        table = self.query_one("#results-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        
        # Add columns
        table.add_columns(
            "Name",
            "Author",
            "Downloads",
            "Endorsements",
            "macOS",
        )
        
        # Hide loading indicator initially
        self.query_one("#loading", LoadingIndicator).display = False
        
        # Check for API key
        app = self.app
        if app.service and not app.service.has_nexus_api_key():
            self.notify(
                "Nexus API key not configured. Go to Settings.",
                severity="warning",
                timeout=5
            )
    
    def watch_is_loading(self, is_loading: bool) -> None:
        """Update UI when loading state changes"""
        self.query_one("#loading", LoadingIndicator).display = is_loading
        self.query_one("#results-table", DataTable).display = not is_loading
    
    def watch_current_page(self, page: int) -> None:
        """Update page indicator"""
        self.query_one("#page-indicator", Static).update(f"Page {page}")
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "search-btn":
            await self.action_search()
        elif event.button.id == "prev-btn":
            await self.action_prev_page()
        elif event.button.id == "next-btn":
            await self.action_next_page()
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search submission"""
        if event.input.id == "nexus-search":
            self.search_query = event.value
            await self.action_search()
    
    @work(exclusive=True)
    async def action_search(self) -> None:
        """Search Nexus Mods"""
        query = self.query_one("#nexus-search", Input).value.strip()
        if not query:
            self.notify("Enter a search term", severity="warning")
            return
        
        self.search_query = query
        self.current_page = 1
        self.is_loading = True
        
        try:
            app = self.app
            if app.service:
                results = await app.service.search_nexus_mods(
                    query,
                    page=self.current_page
                )
                self.search_results = results
                self._update_results_table()
                self.notify(f"Found {len(results)} mods")
        except Exception as e:
            self.notify(f"Search failed: {e}", severity="error")
        finally:
            self.is_loading = False
    
    def _update_results_table(self) -> None:
        """Update results table with search results"""
        table = self.query_one("#results-table", DataTable)
        table.clear()
        
        for mod in self.search_results:
            # Compatibility indicator
            compat = self._get_compatibility_badge(mod)
            
            table.add_row(
                mod.get("name", "Unknown"),
                mod.get("author", "Unknown"),
                self._format_number(mod.get("mod_downloads", 0)),
                self._format_number(mod.get("endorsement_count", 0)),
                compat,
                key=str(mod.get("mod_id"))
            )
    
    def _get_compatibility_badge(self, mod: Dict[str, Any]) -> str:
        """Get macOS compatibility badge for a mod"""
        # This would use the compatibility checker
        # For now, basic heuristic based on file types
        return "[green]✓[/]"  # Placeholder
    
    def _format_number(self, num: int) -> str:
        """Format large numbers"""
        if num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num/1_000:.1f}K"
        return str(num)
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection"""
        if event.row_key:
            mod_id = int(event.row_key.value)
            self.selected_mod = next(
                (m for m in self.search_results if m.get("mod_id") == mod_id),
                None
            )
            self._update_preview()
    
    def _update_preview(self) -> None:
        """Update mod preview panel"""
        preview = self.query_one("#mod-preview", Static)
        if self.selected_mod:
            mod = self.selected_mod
            preview.update(
                f"[bold]{mod.get('name', 'Unknown')}[/]\n"
                f"by {mod.get('author', 'Unknown')}\n\n"
                f"{mod.get('summary', 'No description')[:200]}..."
            )
        else:
            preview.update("")
    
    async def action_install_selected(self) -> None:
        """Install the selected mod"""
        if not self.selected_mod:
            self.notify("No mod selected", severity="warning")
            return
        
        mod_id = self.selected_mod.get("mod_id")
        mod_name = self.selected_mod.get("name", "Unknown")
        
        # Switch to install screen with mod info
        from app.tui.screens.install import InstallScreen
        install_screen = InstallScreen(
            nexus_mod_id=mod_id,
            mod_name=mod_name
        )
        self.app.push_screen(install_screen)
    
    async def action_next_page(self) -> None:
        """Go to next page of results"""
        if self.search_query:
            self.current_page += 1
            await self.action_search()
    
    async def action_prev_page(self) -> None:
        """Go to previous page of results"""
        if self.search_query and self.current_page > 1:
            self.current_page -= 1
            await self.action_search()
    
    def action_focus_search(self) -> None:
        """Focus the search input"""
        self.query_one("#nexus-search", Input).focus()
    
    async def action_refresh(self) -> None:
        """Refresh current search"""
        if self.search_query:
            await self.action_search()
