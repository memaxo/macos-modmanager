"""TUI Screens"""

from app.tui.screens.home import HomeScreen
from app.tui.screens.browse import BrowseScreen
from app.tui.screens.install import InstallScreen
from app.tui.screens.fomod_wizard import FomodWizardScreen
from app.tui.screens.settings import SettingsScreen
from app.tui.screens.help import HelpScreen
from app.tui.screens.mod_detail import ModDetailScreen
from app.tui.screens.dialogs import (
    ConfirmDialog,
    FilePickerDialog,
    FolderPickerDialog,
    ErrorDialog,
)

__all__ = [
    "HomeScreen",
    "BrowseScreen",
    "InstallScreen",
    "FomodWizardScreen",
    "SettingsScreen",
    "HelpScreen",
    "ModDetailScreen",
    "ConfirmDialog",
    "FilePickerDialog",
    "FolderPickerDialog",
    "ErrorDialog",
]
