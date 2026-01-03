"""
Install Progress Widget - Progress tracking for mod installations
"""

from typing import Optional

from textual.app import ComposeResult
from textual.widgets import Static, ProgressBar, Label
from textual.containers import Container, Vertical
from textual.reactive import reactive


class InstallProgress(Container):
    """Composite widget for installation progress tracking"""
    
    # Reactive state
    stage: reactive[str] = reactive("Idle")
    progress: reactive[int] = reactive(0)
    message: reactive[str] = reactive("")
    is_complete: reactive[bool] = reactive(False)
    is_error: reactive[bool] = reactive(False)
    
    # Installation stages
    STAGES = [
        "Validating",
        "Extracting",
        "Analyzing",
        "Staging",
        "Deploying",
        "Finalizing",
    ]
    
    def __init__(
        self,
        title: str = "Installing Mod",
        show_stages: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.title_text = title
        self.show_stages = show_stages
    
    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.title_text, id="progress-title"),
            Container(
                *[Static(f"○ {stage}", id=f"stage-{i}") for i, stage in enumerate(self.STAGES)]
                if self.show_stages else [],
                id="stages-container"
            ),
            ProgressBar(id="main-progress", total=100),
            Static("", id="stage-label"),
            Static("", id="message-label"),
            id="progress-inner"
        )
    
    def watch_stage(self, stage: str) -> None:
        """Update UI when stage changes"""
        self.query_one("#stage-label", Static).update(f"[bold]{stage}[/]")
        
        # Update stage indicators
        if self.show_stages:
            stage_lower = stage.lower()
            for i, stage_name in enumerate(self.STAGES):
                indicator = self.query_one(f"#stage-{i}", Static)
                if stage_name.lower() in stage_lower:
                    indicator.update(f"[cyan]● {stage_name}[/]")
                elif i < self._get_stage_index(stage):
                    indicator.update(f"[green]✓ {stage_name}[/]")
                else:
                    indicator.update(f"[dim]○ {stage_name}[/]")
    
    def _get_stage_index(self, stage: str) -> int:
        """Get the index of the current stage"""
        stage_lower = stage.lower()
        for i, name in enumerate(self.STAGES):
            if name.lower() in stage_lower:
                return i
        return 0
    
    def watch_progress(self, progress: int) -> None:
        """Update progress bar"""
        bar = self.query_one("#main-progress", ProgressBar)
        bar.update(progress=progress)
    
    def watch_message(self, message: str) -> None:
        """Update message label"""
        self.query_one("#message-label", Static).update(message)
    
    def watch_is_complete(self, is_complete: bool) -> None:
        """Handle completion state"""
        if is_complete:
            self.query_one("#stage-label", Static).update(
                "[green bold]Complete![/]"
            )
            if self.show_stages:
                for i in range(len(self.STAGES)):
                    self.query_one(f"#stage-{i}", Static).update(
                        f"[green]✓ {self.STAGES[i]}[/]"
                    )
    
    def watch_is_error(self, is_error: bool) -> None:
        """Handle error state"""
        if is_error:
            self.query_one("#stage-label", Static).update(
                "[red bold]Failed[/]"
            )
    
    def update_progress(self, stage: str, percent: int, message: str = "") -> None:
        """Convenience method to update all progress state"""
        self.stage = stage
        self.progress = percent
        self.message = message
    
    def set_complete(self, message: str = "Installation complete") -> None:
        """Mark installation as complete"""
        self.progress = 100
        self.message = message
        self.is_complete = True
    
    def set_error(self, error: str) -> None:
        """Mark installation as failed"""
        self.message = f"[red]{error}[/]"
        self.is_error = True
    
    def reset(self) -> None:
        """Reset progress widget"""
        self.stage = "Idle"
        self.progress = 0
        self.message = ""
        self.is_complete = False
        self.is_error = False
