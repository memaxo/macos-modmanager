"""
TUI Service Layer

Bridges the Textual TUI with the existing ModManager and other core services.
Provides async-friendly wrappers suitable for use with Textual workers.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Tuple
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session_context
from app.models.mod import Mod, ModFile, ModDependency
from app.models.settings import UserSetting
from app.core.mod_manager import ModManager, ModInstallationError
from app.core.nexus_api import NexusAPIClient, NexusAPIError
from app.core.fomod_parser import FomodParser, detect_fomod, FomodConfig
from app.core.fomod_session import FomodSessionManager, FomodWizardRequired
from app.core.compatibility import CompatibilityChecker
from app.core.backup_manager import BackupManager
from app.config import settings as app_settings

logger = logging.getLogger(__name__)


# Progress callback type
ProgressCallback = Callable[[str, int, str], None]


class TUIModService:
    """
    Service layer for TUI interactions with the mod manager.
    
    Handles database session management, async operations, and provides
    a clean interface for Textual screens to interact with core services.
    """
    
    def __init__(self, game_path: Optional[Path] = None):
        """
        Initialize the TUI service.
        
        Args:
            game_path: Path to the Cyberpunk 2077 installation
        """
        self.game_path = game_path
        self._nexus_client: Optional[NexusAPIClient] = None
        self._fomod_sessions: Dict[str, Dict[str, Any]] = {}
        self._cached_settings: Dict[str, Any] = {}
    
    # ==================== MOD MANAGEMENT ====================
    
    async def get_installed_mods(self) -> List[Mod]:
        """Get all installed (active) mods from the database."""
        async with get_async_session_context() as session:
            result = await session.execute(
                select(Mod).where(Mod.is_active == True).order_by(Mod.name)
            )
            mods = result.scalars().all()
            # Detach from session for use outside context
            for mod in mods:
                session.expunge(mod)
            return list(mods)
    
    async def get_mod_details(self, mod_id: int) -> Optional[Mod]:
        """Get detailed information about a specific mod."""
        async with get_async_session_context() as session:
            result = await session.execute(
                select(Mod).where(Mod.id == mod_id)
            )
            mod = result.scalar_one_or_none()
            
            if not mod:
                return None
            
            # Create a detached copy with the data we need
            mod_data = {
                "id": mod.id,
                "name": mod.name,
                "version": mod.version,
                "mod_type": mod.mod_type,
                "is_enabled": mod.is_enabled,
                "author": mod.author,
                "description": mod.description,
                "file_size": mod.file_size,
                "created_at": mod.install_date,
                "nexus_mod_id": mod.nexus_mod_id,
            }
            
            # Get files
            files_result = await session.execute(
                select(ModFile).where(ModFile.mod_id == mod_id)
            )
            files = files_result.scalars().all()
            files_data = [
                {
                    "path": f.file_path,
                    "size": f.file_size,
                    "deployed": True
                }
                for f in files
            ]
            
            # Get dependencies
            deps_result = await session.execute(
                select(ModDependency).where(ModDependency.mod_id == mod_id)
            )
            deps = deps_result.scalars().all()
            deps_data = [
                {
                    "name": d.dependency_name,
                    "version": d.min_version,
                    "installed": d.is_satisfied
                }
                for d in deps
            ]
        
        # Create a simple object to hold the data (outside async context)
        class ModDetails:
            pass
        
        details = ModDetails()
        for key, value in mod_data.items():
            setattr(details, key, value)
        details.files = files_data
        details.dependencies = deps_data
        
        return details
    
    async def _check_dependency_installed(
        self, session: AsyncSession, dep: ModDependency
    ) -> bool:
        """Check if a dependency is installed."""
        result = await session.execute(
            select(Mod).where(Mod.name.ilike(f"%{dep.dependency_name}%"))
        )
        return result.scalar_one_or_none() is not None
    
    async def toggle_mod(self, mod_id: int) -> bool:
        """
        Toggle a mod's enabled state.
        
        Returns True if mod is now enabled, False if disabled.
        """
        async with get_async_session_context() as session:
            mod_manager = ModManager(session, self.game_path)
            
            # Get current state
            result = await session.execute(
                select(Mod).where(Mod.id == mod_id)
            )
            mod = result.scalar_one_or_none()
            
            if not mod:
                raise ModInstallationError(
                    "MOD_NOT_FOUND",
                    f"Mod with ID {mod_id} not found"
                )
            
            if mod.is_enabled:
                await mod_manager.disable_mod(mod_id)
                return False
            else:
                await mod_manager.enable_mod(mod_id)
                return True
    
    async def uninstall_mod(self, mod_id: int) -> None:
        """Uninstall a mod completely."""
        async with get_async_session_context() as session:
            mod_manager = ModManager(session, self.game_path)
            await mod_manager.uninstall_mod(mod_id)
    
    # ==================== INSTALLATION ====================
    
    async def install_local_mod(
        self,
        file_path: Path,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Optional[Mod]:
        """
        Install a mod from a local archive file.
        
        Args:
            file_path: Path to the mod archive (.zip, .7z, .rar)
            progress_callback: Callback for progress updates (stage, percent, message)
            
        Returns:
            The installed Mod object, or None if installation requires FOMOD wizard
        """
        async with get_async_session_context() as session:
            mod_manager = ModManager(session, self.game_path)
            
            # Wrap callback for ModManager
            def internal_callback(
                stage: str,
                percent: int,
                message: str,
                **kwargs
            ):
                if progress_callback:
                    progress_callback(stage, percent, message)
            
            try:
                mod = await mod_manager.install_mod_from_file(
                    file_path,
                    progress_callback=internal_callback
                )
                return mod
            except FomodWizardRequired as e:
                # Store session for FOMOD wizard
                session_id = str(datetime.now().timestamp())
                self._fomod_sessions[session_id] = {
                    "session_id": session_id,
                    "config": e.fomod_config,
                    "mod_info": e.mod_info,
                    "temp_dir": e.temp_dir
                }
                raise
    
    async def install_from_nexus(
        self,
        mod_id: int,
        file_id: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
        check_compatibility: bool = True
    ) -> Optional[Mod]:
        """
        Download and install a mod from Nexus Mods.
        
        Args:
            mod_id: Nexus Mods mod ID
            file_id: Optional specific file ID (uses latest if not specified)
            progress_callback: Callback for progress updates
            check_compatibility: Whether to check macOS compatibility
        """
        # Ensure API key is loaded into config
        api_key = await self._get_nexus_api_key()
        if not api_key:
            raise ModInstallationError(
                "NEXUS_API_KEY_MISSING",
                "Nexus Mods API key not configured. Set it in Settings or use: mod-manager config set-nexus-key YOUR_KEY"
            )
        
        # Set the API key in config so ModManager can use it
        app_settings.nexus_api_key = api_key
        
        async with get_async_session_context() as session:
            mod_manager = ModManager(session, self.game_path)
            
            # Progress wrapper
            def internal_callback(stage: str, percent: int, message: str, **kwargs):
                if progress_callback:
                    progress_callback(stage, percent, message)
            
            return await mod_manager.install_mod_from_nexus(
                mod_id,
                file_id=file_id,
                check_compatibility=check_compatibility
            )
    
    # ==================== FOMOD HANDLING ====================
    
    async def start_fomod_session(
        self, nexus_mod_id: int
    ) -> Optional[Dict[str, Any]]:
        """Start a new FOMOD installation session."""
        # This would typically download and extract the mod first
        # For now, return stored session if exists
        for session_data in self._fomod_sessions.values():
            if session_data.get("nexus_mod_id") == nexus_mod_id:
                return session_data
        return None
    
    async def get_fomod_session(
        self, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get an existing FOMOD session."""
        return self._fomod_sessions.get(session_id)
    
    async def complete_fomod_install(
        self,
        session_id: str,
        choices: Dict[str, Any]
    ) -> Optional[Mod]:
        """Complete a FOMOD installation with user choices."""
        session_data = self._fomod_sessions.get(session_id)
        if not session_data:
            raise ModInstallationError(
                "FOMOD_SESSION_NOT_FOUND",
                f"FOMOD session {session_id} not found"
            )
        
        async with get_async_session_context() as session:
            mod_manager = ModManager(session, self.game_path)
            
            # Complete installation with choices
            mod = await mod_manager.complete_fomod_installation(
                session_data["temp_dir"],
                session_data["config"],
                choices,
                session_data.get("mod_info", {})
            )
            
            # Clean up session
            del self._fomod_sessions[session_id]
            
            return mod
    
    async def cancel_fomod_session(self, session_id: str) -> None:
        """Cancel and clean up a FOMOD session."""
        session_data = self._fomod_sessions.get(session_id)
        if session_data:
            # Clean up temp directory
            temp_dir = session_data.get("temp_dir")
            if temp_dir and Path(temp_dir).exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            del self._fomod_sessions[session_id]
    
    # ==================== NEXUS MODS SEARCH ====================
    
    async def search_nexus_mods(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20
    ) -> List[Dict[str, Any]]:
        """Search Nexus Mods for Cyberpunk 2077 mods."""
        if not self._nexus_client:
            api_key = await self._get_nexus_api_key()
            if not api_key:
                raise ModInstallationError(
                    "NEXUS_API_KEY_MISSING",
                    "Nexus Mods API key not configured"
                )
            self._nexus_client = NexusAPIClient(api_key)
        
        try:
            results = await self._nexus_client.search_mods(
                query,
                game="cyberpunk2077",
                page=page,
                page_size=page_size
            )
            return results
        except NexusAPIError as e:
            logger.error(f"Nexus search failed: {e}")
            return []
    
    async def get_nexus_mod_info(self, mod_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed info for a Nexus mod."""
        if not self._nexus_client:
            api_key = await self._get_nexus_api_key()
            if not api_key:
                return None
            self._nexus_client = NexusAPIClient(api_key)
        
        try:
            return await self._nexus_client.get_mod("cyberpunk2077", mod_id)
        except NexusAPIError:
            return None
    
    async def get_nexus_mod_files(self, mod_id: int) -> List[Dict[str, Any]]:
        """Get available files/versions for a Nexus mod."""
        if not self._nexus_client:
            api_key = await self._get_nexus_api_key()
            if not api_key:
                raise ModInstallationError(
                    "NEXUS_API_KEY_MISSING",
                    "Nexus Mods API key not configured"
                )
            self._nexus_client = NexusAPIClient(api_key)
        
        try:
            result = await self._nexus_client.get_mod_files("cyberpunk2077", mod_id)
            return result.get("files", [])
        except NexusAPIError as e:
            raise ModInstallationError("NEXUS_API_ERROR", str(e))
    
    def has_nexus_api_key(self) -> bool:
        """Check if Nexus API key is configured."""
        return bool(self._cached_settings.get("nexus_api_key"))
    
    async def test_nexus_api_key(self, api_key: str) -> bool:
        """Test if a Nexus API key is valid."""
        try:
            client = NexusAPIClient(api_key)
            await client.validate_key()
            return True
        except NexusAPIError:
            return False
    
    async def _get_nexus_api_key(self) -> Optional[str]:
        """Get the stored Nexus API key (decrypted if necessary)."""
        from app.utils.security import decrypt_value, is_encrypted
        
        # Check cache first
        if "_decrypted_nexus_api_key" in self._cached_settings:
            return self._cached_settings["_decrypted_nexus_api_key"]
        
        settings = await self.get_settings()
        api_key = settings.get("nexus_api_key")
        
        if not api_key:
            return None
        
        # Decrypt if encrypted
        try:
            if is_encrypted(api_key):
                api_key = decrypt_value(api_key)
        except Exception as e:
            logger.warning(f"Failed to decrypt API key: {e}")
            # Might be stored in plaintext
        
        # Cache the decrypted key
        self._cached_settings["_decrypted_nexus_api_key"] = api_key
        return api_key
    
    # ==================== SETTINGS ====================
    
    async def get_settings(self) -> Dict[str, Any]:
        """Get all application settings."""
        async with get_async_session_context() as session:
            result = await session.execute(select(UserSetting))
            settings_rows = result.scalars().all()
            
            settings_dict = {}
            for row in settings_rows:
                settings_dict[row.key] = row.value
            
            self._cached_settings = settings_dict
            return settings_dict
    
    async def save_settings(self, settings: Dict[str, Any]) -> None:
        """Save application settings."""
        async with get_async_session_context() as session:
            for key, value in settings.items():
                if value is None:
                    continue
                
                # Check if setting exists
                result = await session.execute(
                    select(UserSetting).where(UserSetting.key == key)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    existing.value = str(value) if value is not None else None
                else:
                    new_setting = UserSetting(key=key, value=str(value))
                    session.add(new_setting)
            
            await session.commit()
        
        # Update cached settings
        self._cached_settings.update(settings)
        
        # Handle special settings
        if "custom_game_path" in settings:
            self.game_path = Path(settings["custom_game_path"]) if settings["custom_game_path"] else None
    
    # ==================== COMPATIBILITY ====================
    
    async def check_mod_compatibility(
        self,
        mod_id: int
    ) -> Dict[str, Any]:
        """Check compatibility of an installed mod."""
        async with get_async_session_context() as session:
            result = await session.execute(
                select(Mod).where(Mod.id == mod_id)
            )
            mod = result.scalar_one_or_none()
            
            if not mod:
                return {"compatible": False, "reason": "Mod not found"}
            
            checker = CompatibilityChecker()
            result = await checker.check_mod_compatibility(mod)
            
            return {
                "compatible": result.is_compatible,
                "score": result.compatibility_score,
                "issues": result.issues,
                "warnings": result.warnings
            }
    
    async def check_file_compatibility(
        self,
        file_path: Path
    ) -> Dict[str, Any]:
        """Check compatibility of a mod file before installation."""
        checker = CompatibilityChecker()
        result = await checker.check_mod_file(file_path)
        
        # Build issues list from result fields
        issues = []
        if result.has_dll_files:
            issues.append("Contains Windows DLL files (incompatible)")
        if result.modifies_executable:
            issues.append("Modifies game executable (incompatible)")
        if result.incompatible_dependencies:
            issues.extend([f"Incompatible dependency: {d}" for d in result.incompatible_dependencies])
        
        # Build warnings list
        warnings = []
        if result.has_cet_refs:
            warnings.append("Uses Cyber Engine Tweaks (may need macOS version)")
        if result.has_red4ext_refs and not result.has_dylib_files:
            warnings.append("Uses RED4ext (may need macOS-ported version)")
        
        return {
            "compatible": result.compatible,
            "score": 100 if result.compatible else (50 if result.severity == 'warning' else 0),
            "issues": issues,
            "warnings": warnings,
            "mod_type": self._detect_mod_type(result)
        }
    
    def _detect_mod_type(self, result) -> str:
        """Detect mod type from compatibility result."""
        if result.has_tweak_files:
            return "tweakxl"
        elif result.has_red4ext_plugin or result.has_dylib_files:
            return "red4ext"
        elif result.has_reds_files or result.has_r6_scripts_only:
            return "redscript"
        elif result.has_archivexl_refs:
            return "archivexl"
        return "unknown"
    
    # ==================== BACKUP ====================
    
    async def create_backup(
        self,
        backup_name: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Optional[str]:
        """Create a backup of current game state."""
        backup_manager = BackupManager(self.game_path)
        
        def callback(percent: int, message: str):
            if progress_callback:
                progress_callback("Backing up", percent, message)
        
        backup_id = await backup_manager.create_backup(
            name=backup_name,
            progress_callback=callback
        )
        return backup_id
    
    async def restore_backup(
        self,
        backup_id: str,
        progress_callback: Optional[ProgressCallback] = None
    ) -> bool:
        """Restore from a backup."""
        backup_manager = BackupManager(self.game_path)
        
        def callback(percent: int, message: str):
            if progress_callback:
                progress_callback("Restoring", percent, message)
        
        return await backup_manager.restore_backup(
            backup_id,
            progress_callback=callback
        )
    
    async def list_backups(self) -> List[Dict[str, Any]]:
        """List available backups."""
        backup_manager = BackupManager(self.game_path)
        return await backup_manager.list_backups()
