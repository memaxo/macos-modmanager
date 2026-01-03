"""
FOMOD Wizard Screen - Interactive Mod Configuration

Guides users through FOMOD installer choices step by step.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Footer, Static, Button, RadioSet, RadioButton,
    Checkbox, Label, RichLog
)
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual import work


class FomodWizardScreen(Screen):
    """FOMOD configuration wizard"""
    
    BINDINGS = [
        Binding("left", "prev_step", "Back"),
        Binding("right", "next_step", "Next"),
        Binding("enter", "next_step", "Continue"),
        Binding("escape", "cancel", "Cancel"),
    ]
    
    # Reactive state
    current_step: reactive[int] = reactive(0)
    total_steps: reactive[int] = reactive(0)
    is_loading: reactive[bool] = reactive(False)
    can_go_back: reactive[bool] = reactive(False)
    can_go_next: reactive[bool] = reactive(True)
    is_final_step: reactive[bool] = reactive(False)
    
    def __init__(
        self,
        nexus_mod_id: Optional[int] = None,
        session_id: Optional[str] = None,
        temp_dir: Optional[Path] = None,
        name: str = "fomod-wizard"
    ):
        super().__init__(name=name)
        self.nexus_mod_id = nexus_mod_id
        self.session_id = session_id
        self.temp_dir = temp_dir
        
        # FOMOD data
        self.fomod_config = None
        self.mod_info: Dict[str, Any] = {}
        self.choices: Dict[str, Any] = {"type": "fomod", "options": []}
        self.visible_steps: List[int] = []
    
    def compose(self) -> ComposeResult:
        """Create the wizard layout"""
        yield Container(
            # Header with progress
            Horizontal(
                Static("FOMOD Installer", id="wizard-title", classes="screen-title"),
                Static("Step 0 of 0", id="step-indicator"),
                id="wizard-header"
            ),
            
            # Mod info banner
            Container(
                Static("", id="mod-name"),
                Static("", id="mod-description"),
                id="mod-info-banner"
            ),
            
            # Main content area - scrollable
            VerticalScroll(
                Static("", id="step-name"),
                Container(id="choices-container"),
                id="step-content"
            ),
            
            # Navigation buttons
            Horizontal(
                Button("← Back", id="back-btn", disabled=True),
                Button("Cancel", id="cancel-btn", variant="error"),
                Button("Next →", id="next-btn", variant="primary"),
                id="wizard-nav"
            ),
            
            id="wizard-container"
        )
        yield Footer()
    
    async def on_mount(self) -> None:
        """Initialize the wizard"""
        self.is_loading = True
        
        # Load FOMOD configuration
        await self._load_fomod_config()
    
    async def _load_fomod_config(self) -> None:
        """Load FOMOD configuration from session or mod"""
        try:
            app = self.app
            if app.service:
                if self.session_id:
                    # Resume existing session
                    session_data = await app.service.get_fomod_session(self.session_id)
                    if session_data:
                        self.fomod_config = session_data["config"]
                        self.mod_info = session_data["mod_info"]
                        self.temp_dir = session_data["temp_dir"]
                        self.choices = session_data.get("choices", {"type": "fomod", "options": []})
                elif self.nexus_mod_id:
                    # Start new session from Nexus mod
                    session_data = await app.service.start_fomod_session(self.nexus_mod_id)
                    if session_data:
                        self.session_id = session_data["session_id"]
                        self.fomod_config = session_data["config"]
                        self.mod_info = session_data["mod_info"]
                        self.temp_dir = session_data["temp_dir"]
                
                if self.fomod_config:
                    self._setup_wizard()
                else:
                    self.notify("Failed to load FOMOD configuration", severity="error")
                    self.app.pop_screen()
        except Exception as e:
            self.notify(f"Error loading FOMOD: {e}", severity="error")
            self.app.pop_screen()
        finally:
            self.is_loading = False
    
    def _setup_wizard(self) -> None:
        """Set up wizard with FOMOD config"""
        # Update mod info
        self.query_one("#mod-name", Static).update(
            f"[bold]{self.mod_info.get('name', 'Unknown Mod')}[/]"
        )
        self.query_one("#mod-description", Static).update(
            self.fomod_config.info.description[:200] if self.fomod_config.info.description else ""
        )
        
        # Calculate visible steps
        self.visible_steps = list(range(len(self.fomod_config.steps)))
        self.total_steps = len(self.visible_steps)
        
        if self.total_steps > 0:
            self._render_step(0)
        else:
            # No steps - just required files
            self.is_final_step = True
            self._render_summary()
    
    def _render_step(self, step_idx: int) -> None:
        """Render a specific step"""
        if step_idx >= len(self.visible_steps):
            return
        
        actual_idx = self.visible_steps[step_idx]
        step = self.fomod_config.steps[actual_idx]
        
        # Update header
        self.query_one("#step-indicator", Static).update(
            f"Step {step_idx + 1} of {self.total_steps}"
        )
        self.query_one("#step-name", Static).update(f"[bold]{step.name}[/]")
        
        # Update navigation state
        self.current_step = step_idx
        self.can_go_back = step_idx > 0
        self.is_final_step = step_idx == self.total_steps - 1
        
        self.query_one("#back-btn", Button).disabled = not self.can_go_back
        self.query_one("#next-btn", Button).label = "Install" if self.is_final_step else "Next →"
        
        # Clear and populate choices container
        container = self.query_one("#choices-container", Container)
        container.remove_children()
        
        # Render groups
        for group in step.groups:
            self._render_group(container, group, actual_idx)
    
    def _render_group(self, container: Container, group, step_idx: int) -> None:
        """Render a single option group"""
        from textual.widgets import RadioSet, RadioButton, Checkbox
        
        # Group header
        group_label = Static(f"[bold cyan]{group.name}[/]", classes="group-name")
        container.mount(group_label)
        
        # Determine selection type
        group_type = group.type.value if hasattr(group.type, 'value') else str(group.type)
        
        if "exactly_one" in group_type.lower() or "at_most_one" in group_type.lower():
            # Radio buttons
            radio_set = RadioSet(id=f"group-{step_idx}-{group.name}")
            for i, plugin in enumerate(group.plugins):
                radio_btn = RadioButton(
                    plugin.name,
                    id=f"plugin-{step_idx}-{group.name}-{i}"
                )
                radio_set.mount(radio_btn)
            container.mount(radio_set)
        else:
            # Checkboxes for multi-select
            for i, plugin in enumerate(group.plugins):
                checkbox = Checkbox(
                    plugin.name,
                    id=f"plugin-{step_idx}-{group.name}-{i}"
                )
                container.mount(checkbox)
    
    def _render_summary(self) -> None:
        """Render final summary before install"""
        self.query_one("#step-indicator", Static).update("Summary")
        self.query_one("#step-name", Static).update("[bold]Review and Install[/]")
        
        container = self.query_one("#choices-container", Container)
        container.remove_children()
        
        # Show summary of choices
        summary = Static(self._format_choices_summary())
        container.mount(summary)
        
        self.query_one("#next-btn", Button).label = "Install"
        self.is_final_step = True
    
    def _format_choices_summary(self) -> str:
        """Format choices for summary display"""
        lines = ["[bold]Selected Options:[/]\n"]
        
        for step_choice in self.choices.get("options", []):
            step_name = step_choice.get("name", "Unknown Step")
            lines.append(f"[cyan]{step_name}[/]")
            
            for group in step_choice.get("groups", []):
                group_name = group.get("name", "Unknown Group")
                for choice in group.get("choices", []):
                    choice_name = choice.get("name", "Unknown")
                    lines.append(f"  • {choice_name}")
            lines.append("")
        
        if not self.choices.get("options"):
            lines.append("[dim]No options selected (using defaults)[/]")
        
        return "\n".join(lines)
    
    def _collect_current_choices(self) -> Dict[str, Any]:
        """Collect choices from current step"""
        if self.current_step >= len(self.visible_steps):
            return {}
        
        actual_idx = self.visible_steps[self.current_step]
        step = self.fomod_config.steps[actual_idx]
        
        step_choices = {
            "name": step.name,
            "groups": []
        }
        
        for group in step.groups:
            group_choices = {
                "name": group.name,
                "choices": []
            }
            
            group_type = group.type.value if hasattr(group.type, 'value') else str(group.type)
            
            if "exactly_one" in group_type.lower() or "at_most_one" in group_type.lower():
                # Check RadioSet
                try:
                    radio_set = self.query_one(f"#group-{actual_idx}-{group.name}", RadioSet)
                    if radio_set.pressed_button:
                        btn_id = radio_set.pressed_button.id
                        idx = int(btn_id.split("-")[-1])
                        plugin = group.plugins[idx]
                        group_choices["choices"].append({
                            "name": plugin.name,
                            "idx": idx
                        })
                except Exception:
                    pass
            else:
                # Check Checkboxes
                for i, plugin in enumerate(group.plugins):
                    try:
                        checkbox = self.query_one(f"#plugin-{actual_idx}-{group.name}-{i}", Checkbox)
                        if checkbox.value:
                            group_choices["choices"].append({
                                "name": plugin.name,
                                "idx": i
                            })
                    except Exception:
                        pass
            
            if group_choices["choices"]:
                step_choices["groups"].append(group_choices)
        
        return step_choices
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "back-btn":
            await self.action_prev_step()
        elif event.button.id == "next-btn":
            await self.action_next_step()
        elif event.button.id == "cancel-btn":
            await self.action_cancel()
    
    async def action_prev_step(self) -> None:
        """Go to previous step"""
        if self.current_step > 0:
            self._render_step(self.current_step - 1)
    
    async def action_next_step(self) -> None:
        """Go to next step or finish"""
        # Collect current choices
        current_choices = self._collect_current_choices()
        if current_choices:
            # Update or add to choices
            while len(self.choices["options"]) <= self.current_step:
                self.choices["options"].append({})
            self.choices["options"][self.current_step] = current_choices
        
        if self.is_final_step:
            # Perform installation
            await self._finish_install()
        elif self.current_step < self.total_steps - 1:
            self._render_step(self.current_step + 1)
        else:
            # Show summary
            self._render_summary()
    
    async def _finish_install(self) -> None:
        """Complete the FOMOD installation"""
        self.notify("Installing with selected options...")
        
        try:
            app = self.app
            if app.service and self.session_id:
                mod = await app.service.complete_fomod_install(
                    self.session_id,
                    self.choices
                )
                
                if mod:
                    self.notify(f"Successfully installed {mod.name}", severity="information")
                    self.app.pop_screen()
                else:
                    self.notify("Installation completed", severity="information")
                    self.app.pop_screen()
        except Exception as e:
            self.notify(f"Installation failed: {e}", severity="error")
    
    async def action_cancel(self) -> None:
        """Cancel the wizard"""
        # Clean up session
        try:
            app = self.app
            if app.service and self.session_id:
                await app.service.cancel_fomod_session(self.session_id)
        except Exception:
            pass
        
        self.notify("Installation cancelled")
        self.app.pop_screen()
