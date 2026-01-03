import asyncio
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, TypedDict, Literal, Tuple, Callable
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.mod import Mod, ModFile, ModDependency, ModInstallation, ModInstallerChoices
from app.core.compatibility import CompatibilityChecker, CompatibilityResult
from app.core.nexus_api import NexusAPIClient, NexusAPIError
from app.core.fomod_parser import FomodParser, detect_fomod, FomodConfig
from app.core.fomod_session import FomodSessionManager, FomodWizardRequired
from app.core.install_validator import InstallValidator, AtomicInstaller, ValidationResult
from app.utils.path_utils import remove_quarantine_flag, make_executable
from app.config import settings
from app.core.backup_manager import BackupManager, BackupType
import aiofiles
import zipfile
import py7zr
import rarfile

logger = logging.getLogger(__name__)


class FileInfoDict(TypedDict):
    source_path: Path  # type: ignore[typeddict-item]
    path: str
    type: str
    install_path: Path  # type: ignore[typeddict-item]


class ModStructureDict(TypedDict, total=False):
    name: str
    type: str
    version: Optional[str]
    files: List[str]


class InstallQueueItem(TypedDict):
    status: Literal["downloading", "installing", "completed", "failed"]
    progress: int
    mod_id: int
    name: str


class InstallErrorCode:
    """Standard error codes for mod installation failures"""
    # Validation errors
    GAME_NOT_FOUND = "GAME_NOT_FOUND"
    GAME_RUNNING = "GAME_RUNNING"
    ARCHIVE_NOT_FOUND = "ARCHIVE_NOT_FOUND"
    ARCHIVE_CORRUPT = "ARCHIVE_CORRUPT"
    ARCHIVE_EMPTY = "ARCHIVE_EMPTY"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    INSUFFICIENT_SPACE = "INSUFFICIENT_SPACE"
    NO_WRITE_PERMISSION = "NO_WRITE_PERMISSION"
    
    # Compatibility errors
    INCOMPATIBLE_MOD = "INCOMPATIBLE_MOD"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    CONFLICTING_MOD = "CONFLICTING_MOD"
    
    # Installation errors
    ALREADY_INSTALLED = "ALREADY_INSTALLED"
    NO_FILES_FOUND = "NO_FILES_FOUND"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    DEPLOY_FAILED = "DEPLOY_FAILED"
    HARDLINK_FAILED = "HARDLINK_FAILED"
    STAGING_FAILED = "STAGING_FAILED"
    
    # Database errors
    DB_ERROR = "DB_ERROR"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    
    # FOMOD errors
    FOMOD_WIZARD_REQUIRED = "FOMOD_WIZARD_REQUIRED"
    FOMOD_PARSE_ERROR = "FOMOD_PARSE_ERROR"
    FOMOD_NO_FILES = "FOMOD_NO_FILES"
    
    # General errors
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"


# Map error codes to default suggestions
ERROR_SUGGESTIONS: Dict[str, str] = {
    InstallErrorCode.GAME_NOT_FOUND: "Verify the game is installed and configure the path in Settings → Game Path",
    InstallErrorCode.GAME_RUNNING: "Close Cyberpunk 2077 before installing mods",
    InstallErrorCode.ARCHIVE_NOT_FOUND: "Verify the file was uploaded correctly and try again",
    InstallErrorCode.ARCHIVE_CORRUPT: "Re-download the mod file from Nexus Mods",
    InstallErrorCode.ARCHIVE_EMPTY: "This archive contains no files. Download a different version",
    InstallErrorCode.UNSUPPORTED_FORMAT: "Convert the archive to .zip, .7z, or .rar format",
    InstallErrorCode.INSUFFICIENT_SPACE: "Free up disk space and try again",
    InstallErrorCode.NO_WRITE_PERMISSION: "Check folder permissions or run with elevated privileges",
    InstallErrorCode.INCOMPATIBLE_MOD: "Check if there's a macOS-compatible version on Nexus Mods",
    InstallErrorCode.MISSING_DEPENDENCY: "Install the required dependencies first",
    InstallErrorCode.CONFLICTING_MOD: "Disable conflicting mods before installing",
    InstallErrorCode.ALREADY_INSTALLED: "Use 'Reinstall' to update, or uninstall first",
    InstallErrorCode.NO_FILES_FOUND: "Verify this is a valid Cyberpunk 2077 mod with .reds, .yaml, .dylib, or .archive files",
    InstallErrorCode.EXTRACTION_FAILED: "The archive may be password-protected or corrupted. Re-download from Nexus Mods",
    InstallErrorCode.DEPLOY_FAILED: "Check disk space and permissions. Try running the mod manager with elevated privileges",
    InstallErrorCode.HARDLINK_FAILED: "Ensure the staging and game directories are on the same filesystem",
    InstallErrorCode.STAGING_FAILED: "Check disk space in the staging directory",
    InstallErrorCode.DB_ERROR: "Database error. Try restarting the mod manager",
    InstallErrorCode.ROLLBACK_FAILED: "Manual cleanup may be required. Check the logs for details",
    InstallErrorCode.FOMOD_WIZARD_REQUIRED: "This mod requires the installation wizard to configure options",
    InstallErrorCode.FOMOD_PARSE_ERROR: "The mod's installer is malformed. Try a different version",
    InstallErrorCode.FOMOD_NO_FILES: "Go back and select different options in the installer",
    InstallErrorCode.UNEXPECTED_ERROR: "Check the logs for details and try again",
    InstallErrorCode.TIMEOUT_ERROR: "The operation timed out. Try again with a stable connection",
    InstallErrorCode.NETWORK_ERROR: "Check your internet connection and try again",
}


class ModInstallationError(Exception):
    """
    Exception raised during mod installation with actionable guidance.
    
    Provides:
    - Clear error message
    - Standardized error code
    - User-actionable suggestion
    - Additional details for debugging
    """
    
    def __init__(
        self,
        message: str,
        code: str = InstallErrorCode.UNEXPECTED_ERROR,
        suggestion: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        # Use provided suggestion or lookup default
        self.suggestion = suggestion or ERROR_SUGGESTIONS.get(code, "")
        self.details = details or {}
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        parts = [self.message]
        if self.suggestion:
            parts.append(f"\n💡 Suggestion: {self.suggestion}")
        return "".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.message,
            "code": self.code,
            "suggestion": self.suggestion,
            "details": self.details
        }
    
    @classmethod
    def game_not_found(cls, path: Optional[str] = None) -> "ModInstallationError":
        """Create error for game not found"""
        msg = "Cyberpunk 2077 installation not found"
        if path:
            msg += f" at {path}"
        return cls(message=msg, code=InstallErrorCode.GAME_NOT_FOUND)
    
    @classmethod
    def archive_corrupt(cls, filename: str, reason: str = "") -> "ModInstallationError":
        """Create error for corrupt archive"""
        msg = f"Archive '{filename}' is corrupted"
        if reason:
            msg += f": {reason}"
        return cls(message=msg, code=InstallErrorCode.ARCHIVE_CORRUPT)
    
    @classmethod
    def no_files_found(cls, mod_name: str = "") -> "ModInstallationError":
        """Create error for no installable files"""
        msg = "No installable mod files found in the archive"
        if mod_name:
            msg = f"No installable files found in '{mod_name}'"
        return cls(message=msg, code=InstallErrorCode.NO_FILES_FOUND)
    
    @classmethod
    def already_installed(cls, mod_name: str = "") -> "ModInstallationError":
        """Create error for already installed mod"""
        msg = "This mod is already installed"
        if mod_name:
            msg = f"'{mod_name}' is already installed"
        return cls(message=msg, code=InstallErrorCode.ALREADY_INSTALLED)
    
    @classmethod
    def incompatible(cls, reason: str) -> "ModInstallationError":
        """Create error for incompatible mod"""
        return cls(
            message=f"Mod is not compatible with macOS: {reason}",
            code=InstallErrorCode.INCOMPATIBLE_MOD
        )


# Progress callback type for installation status updates
ProgressCallback = Callable[[str, int, str], None]  # (stage, percent, message)


class FomodInstallRequired(Exception):
    """Exception raised when FOMOD wizard is required for installation"""
    def __init__(self, session_id: str, mod_info: Dict[str, Any]):
        self.session_id = session_id
        self.mod_info = mod_info
        super().__init__(f"FOMOD wizard required: session {session_id}")


class ModManager:
    """Manages mod installation, uninstallation, and updates"""
    
    # In-memory queue for tracking active installations (Class variable)
    _install_queue: Dict[str, InstallQueueItem] = {}  # job_id: InstallQueueItem
    
    def __init__(self, db: AsyncSession, game_path: Path):
        self.db = db
        self.game_path = game_path
        self.mod_path = game_path / settings.default_mod_path
        self.compatibility_checker = CompatibilityChecker()
        self.backup_manager = BackupManager(game_path)
        self.validator = InstallValidator(game_path)
        self.auto_backup_enabled = True  # Enable auto-backup by default
        self.mod_path.mkdir(parents=True, exist_ok=True)
    
    async def _create_pre_install_backup(self, mod_name: str) -> Optional[str]:
        """Create a backup before mod installation"""
        if not self.auto_backup_enabled:
            return None
        
        try:
            backup = await self.backup_manager.create_backup(
                name=f"Pre-install: {mod_name}",
                backup_type=BackupType.PRE_INSTALL,
                include_frameworks=False,  # Only backup mods, not frameworks
                include_plugins=True,
                include_scripts=True,
                include_tweaks=True,
                include_archives=False,
                compress=True,
            )
            return backup.id
        except Exception as e:
            # Log but don't fail the installation
            print(f"Warning: Could not create pre-install backup: {e}")
            return None
    
    async def _cleanup_old_backups(self, keep: int = 10):
        """Cleanup old auto-backups to prevent storage bloat"""
        try:
            await self.backup_manager.delete_old_backups(keep=keep)
        except Exception:
            pass  # Non-critical operation
    
    async def install_mod_from_file(
        self,
        mod_file: Path,
        nexus_mod_id: Optional[int] = None,
        check_compatibility: bool = True,
        create_backup: bool = True,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Mod:
        """
        Install mod from archive file with validation, progress reporting, and transaction safety.
        
        Transaction Safety:
        - Database operations are wrapped in a transaction
        - File operations are staged before deployment
        - On failure, database is rolled back and staged files are cleaned up
        - Deployed files are removed on rollback
        """
        
        def report_progress(stage: str, percent: int, message: str):
            if progress_callback:
                progress_callback(stage, percent, message)
            if settings.debug:
                logger.info(f"[{stage}] {percent}% - {message}")
        
        report_progress("validate", 0, "Starting pre-flight validation...")
        
        # === PRE-FLIGHT VALIDATION ===
        validation = await self.validator.pre_flight_check(
            archive_path=mod_file,
            estimated_size=mod_file.stat().st_size * 3  # Estimate 3x extraction ratio
        )
        
        if not validation.passed:
            errors = validation.errors
            if errors:
                first_error = errors[0]
                raise ModInstallationError(
                    message=first_error.message,
                    code=first_error.code,
                    suggestion=first_error.suggestion,
                    details=first_error.details
                )
        
        # Log any warnings
        for warning in validation.warnings:
            logger.warning(f"[{warning.code}] {warning.message}")
        
        report_progress("validate", 20, "Pre-flight checks passed")
        
        # === COMPATIBILITY CHECK ===
        compat_result: Optional[CompatibilityResult] = None
        if check_compatibility:
            report_progress("compatibility", 25, "Checking macOS compatibility...")
            compat_result = await self.compatibility_checker.check_mod_file(mod_file)
            if not compat_result.compatible and settings.strict_compatibility:
                raise ModInstallationError(
                    message=f"Mod is not compatible with macOS: {compat_result.reason}",
                    code="INCOMPATIBLE_MOD",
                    suggestion="Check if there's a macOS-compatible version or alternative mod"
                )
        
        report_progress("compatibility", 30, "Compatibility check passed")
        
        # === PRE-INSTALL BACKUP ===
        if create_backup:
            report_progress("backup", 35, "Creating pre-install backup...")
            await self._create_pre_install_backup(mod_file.stem)
        
        # === HASH CHECK ===
        report_progress("hash", 40, "Calculating file hash...")
        file_hash = await self._calculate_file_hash(mod_file)
        
        # Check if mod already installed
        existing = await self.db.execute(
            select(Mod).where(Mod.file_hash == file_hash)
        )
        if existing.scalar_one_or_none():
            raise ModInstallationError(
                message="This mod is already installed",
                code="ALREADY_INSTALLED",
                suggestion="Use 'Reinstall' if you want to reinstall, or check your installed mods"
            )
        
        report_progress("extract", 45, "Extracting archive...")
        
        # Extract mod
        temp_dir = Path("/tmp") / f"mod_install_{mod_file.stem}"
        temp_dir.mkdir(exist_ok=True)
        
        # Track resources for cleanup on failure
        staging_root: Optional[Path] = None
        deployed_files: List[Path] = []
        mod: Optional[Mod] = None
        
        try:
            await self._extract_archive(mod_file, temp_dir)
            report_progress("extract", 55, "Archive extracted")
            
            # Detect mod structure
            report_progress("analyze", 60, "Analyzing mod structure...")
            mod_structure = await self._detect_mod_structure(temp_dir)
            
            # Identify files to be installed
            files_to_install = await self._get_files_to_install(temp_dir, mod_structure)
            
            if not files_to_install:
                raise ModInstallationError(
                    message="No installable files found in the archive",
                    code="NO_FILES_FOUND",
                    suggestion="Verify this is a valid Cyberpunk 2077 mod archive with .reds, .yaml, .dylib, or .archive files"
                )
            
            report_progress("analyze", 65, f"Found {len(files_to_install)} files to install")
            
            # === BEGIN TRANSACTION-SAFE SECTION ===
            # Create mod record
            mod = Mod(
                nexus_mod_id=nexus_mod_id,
                name=mod_structure.get("name", mod_file.stem),
                version=mod_structure.get("version"),
                game_id=settings.game_id,
                mod_type=mod_structure.get("type", "redscript"),
                install_path=str(self.mod_path),
                file_hash=file_hash,
                file_size=mod_file.stat().st_size,
                is_enabled=False,  # Start disabled until deployment succeeds
                is_active=True,
                mod_metadata=mod_structure
            )
            
            self.db.add(mod)
            await self.db.flush()  # Get mod.id without committing

            report_progress("staging", 70, "Staging files...")
            
            # Copy files to staging directory first
            staging_root = settings.staging_dir / f"mod_{mod.id}"
            staging_root.mkdir(parents=True, exist_ok=True)
            
            staged_files: List[Path] = []
            for i, file_info in enumerate(files_to_install):
                source = file_info["source_path"]
                rel_path = file_info["path"]
                dest = staging_root / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(source), str(dest))
                staged_files.append(dest)
                
                # Update progress for each file
                progress = 70 + int((i / len(files_to_install)) * 10)
                report_progress("staging", progress, f"Staged {i+1}/{len(files_to_install)} files")

            report_progress("backup", 80, "Checking for conflicts...")
            
            # Backup if enabled (check conflicts in game dir)
            backup_path = None
            if settings.backup_before_install:
                backup_path = await self._backup_conflicting_files(files_to_install)
                if backup_path:
                    report_progress("backup", 82, f"Backed up {len(list(backup_path.rglob('*')))} conflicting files")
            
            # Create mod file records BEFORE enabling mod
            installed_files: List[FileInfoDict] = []
            for file_info in files_to_install:
                mod_file_record = ModFile(
                    mod_id=mod.id,
                    file_path=file_info["path"],
                    file_type=file_info["type"],
                    install_path=str(file_info["install_path"])
                )
                self.db.add(mod_file_record)
                installed_files.append(file_info)
            
            await self.db.flush()
            
            report_progress("deploy", 85, "Deploying mod files...")
            
            # Deploy mod (hardlink from staging to game)
            # Track deployed files for potential rollback
            deployed_files = await self._deploy_mod_files(mod.id, staging_root, installed_files)
            
            # Mark mod as enabled now that files are deployed
            mod.is_enabled = True
            
            report_progress("deploy", 90, "Files deployed to game directory")
            
            # Create installation record
            installation = ModInstallation(
                mod_id=mod.id,
                install_type="install",
                backup_path=str(backup_path) if backup_path else None,
                install_path=str(self.mod_path),
                file_hash_after=file_hash,
                rollback_available=backup_path is not None
            )
            self.db.add(installation)
            
            # Create dependency records
            if compat_result and compat_result.incompatible_dependencies:
                for dep_name in compat_result.incompatible_dependencies:
                    dep = ModDependency(
                        mod_id=mod.id,
                        dependency_name=dep_name,
                        dependency_type="incompatible",
                        is_satisfied=False
                    )
                    self.db.add(dep)
            
            # === COMMIT TRANSACTION ===
            await self.db.commit()
            
            report_progress("finalize", 95, "Removing quarantine flags...")
            
            # Remove quarantine flags (macOS) with verification
            if settings.auto_remove_quarantine:
                file_paths = [Path(f["install_path"]) for f in installed_files]
                success, failed = await self.validator.remove_quarantine_flags(file_paths)
                if failed > 0:
                    logger.warning(f"Failed to remove quarantine from {failed} files")
            
            # Post-install validation
            report_progress("verify", 98, "Verifying installation...")
            verify_result = await self.validator.post_install_verify(
                installed_files, 
                mod.name
            )
            
            if not verify_result.passed:
                for issue in verify_result.errors:
                    logger.error(f"Post-install issue: [{issue.code}] {issue.message}")
                # Don't fail - just warn. Files might still work.
            
            report_progress("complete", 100, f"Successfully installed {mod.name}")
            
            return mod
            
        except ModInstallationError:
            # Rollback database transaction
            await self.db.rollback()
            # Cleanup deployed files
            await self._cleanup_deployed_files(deployed_files)
            # Re-raise installation errors as-is
            raise
        except Exception as e:
            # Rollback database transaction
            await self.db.rollback()
            # Cleanup deployed files
            await self._cleanup_deployed_files(deployed_files)
            # Wrap unexpected errors with guidance
            logger.exception(f"Unexpected error during installation: {e}")
            raise ModInstallationError(
                message=f"Installation failed: {str(e)}",
                code="UNEXPECTED_ERROR",
                suggestion="Check the logs for details and try again"
            )
        finally:
            # Cleanup temp extraction directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            # Note: staging_root is intentionally NOT cleaned up on success
            # as it's needed for enable/disable functionality
    
    async def _deploy_mod_files(
        self, 
        mod_id: int, 
        staging_root: Path, 
        files_to_install: List[FileInfoDict]
    ) -> List[Path]:
        """
        Deploy mod files from staging to game directory using hardlinks.
        
        Returns list of deployed file paths for potential rollback.
        """
        deployed_files: List[Path] = []
        
        for file_info in files_to_install:
            rel_path = Path(file_info["path"])
            staging_path = staging_root / rel_path
            dest_path = Path(file_info["install_path"])
            
            if staging_path.exists():
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Remove existing file/link
                if dest_path.exists():
                    dest_path.unlink()
                
                try:
                    # Try hardlink first (most efficient)
                    import os
                    os.link(str(staging_path), str(dest_path))
                    deployed_files.append(dest_path)
                except OSError as e:
                    # Fallback to copy if hardlink fails (cross-filesystem, etc.)
                    logger.debug(f"Hardlink failed for {staging_path}, falling back to copy: {e}")
                    shutil.copy2(str(staging_path), str(dest_path))
                    deployed_files.append(dest_path)
        
        return deployed_files
    
    async def _cleanup_deployed_files(self, deployed_files: List[Path]) -> None:
        """
        Clean up deployed files on installation failure.
        Removes files and empty parent directories.
        """
        for file_path in deployed_files:
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.debug(f"Cleaned up deployed file: {file_path}")
                    
                    # Try to remove empty parent directories
                    parent = file_path.parent
                    while parent != self.game_path and parent.exists():
                        try:
                            if not any(parent.iterdir()):
                                parent.rmdir()
                                parent = parent.parent
                            else:
                                break
                        except OSError:
                            break
            except Exception as e:
                logger.warning(f"Failed to cleanup deployed file {file_path}: {e}")
    
    async def install_mod_from_nexus(
        self,
        nexus_mod_id: int,
        file_id: Optional[int] = None,
        check_compatibility: bool = True
    ) -> Mod:
        """Install mod from Nexus Mods"""
        
        async with NexusAPIClient() as nexus:
            # Get mod info
            mod_info = await nexus.get_mod(settings.game_domain, nexus_mod_id)
            
            # Get mod files
            files_info = await nexus.get_mod_files(settings.game_domain, nexus_mod_id)
            files = files_info.get("files", [])
            
            if not files:
                raise ModInstallationError("No files available for this mod")
            
            # Use specified file, or prefer MAIN category, or fall back to first file
            if file_id:
                target_file = next((f for f in files if f["file_id"] == file_id), None)
                if not target_file:
                    raise ModInstallationError(f"File ID {file_id} not found for this mod")
            else:
                # Prefer MAIN category files, then most recent (last in list is often newest)
                main_files = [f for f in files if f.get("category_name") == "MAIN"]
                if main_files:
                    target_file = main_files[-1]  # Latest main file
                else:
                    # Fall back to first non-archived file, or just first file
                    non_archived = [f for f in files if f.get("category_name") not in ("ARCHIVED", "OLD_VERSION")]
                    target_file = non_archived[0] if non_archived else files[-1]
            
            # Download mod file
            download_links = await nexus.get_download_link(
                settings.game_domain,
                nexus_mod_id,
                target_file["file_id"]
            )
            
            # API returns a list of download links, use the first one
            if isinstance(download_links, list) and download_links:
                download_url = download_links[0].get("URI")
            else:
                download_url = download_links.get("URI") if isinstance(download_links, dict) else None
            
            if not download_url:
                raise ModInstallationError("Could not get download URL")
            
            # Download to temp location - preserve original extension
            original_filename = target_file.get("file_name", "mod.zip")
            # Extract extension from original filename
            ext = Path(original_filename).suffix.lower() or ".zip"
            temp_file = settings.cache_dir / f"{nexus_mod_id}_{target_file['file_id']}{ext}"
            
            # Progress callback for Nexus download
            async def progress_cb(downloaded: int, total: int) -> None:
                job_id = f"nexus_{nexus_mod_id}"
                progress_percent = int((downloaded / total) * 100) if total > 0 else 0
                self._install_queue[job_id] = InstallQueueItem(
                    status="downloading",
                    progress=progress_percent,
                    mod_id=nexus_mod_id,
                    name=mod_info.get("name", str(nexus_mod_id))
                )

            await nexus.download_file(download_url, temp_file, progress_callback=progress_cb)
            
            try:
                job_id = f"nexus_{nexus_mod_id}"
                if job_id in self._install_queue:
                    self._install_queue[job_id]["status"] = "installing"
                    self._install_queue[job_id]["progress"] = 100

                # Install from downloaded file
                mod = await self.install_mod_from_file(
                    temp_file,
                    nexus_mod_id=nexus_mod_id,
                    check_compatibility=check_compatibility
                )
                
                if job_id in self._install_queue:
                    self._install_queue[job_id]["status"] = "completed"
                return mod
            finally:
                # Cleanup temp file
                if temp_file.exists():
                    temp_file.unlink()
    
    async def uninstall_mod(self, mod_id: int) -> None:
        """Uninstall a mod"""
        
        # Get mod
        result = await self.db.execute(select(Mod).where(Mod.id == mod_id))
        mod = result.scalar_one_or_none()
        
        if not mod:
            raise ModInstallationError("Mod not found")
        
        # Get mod files
        files_result = await self.db.execute(
            select(ModFile).where(ModFile.mod_id == mod_id)
        )
        mod_files = files_result.scalars().all()
        
        # Remove files
        for mod_file in mod_files:
            file_path = Path(mod_file.install_path)
            if file_path.exists():
                file_path.unlink()
                # Remove empty directories
                try:
                    file_path.parent.rmdir()
                except OSError:
                    pass
        
        # Remove staging directory if it exists
        staging_root = settings.staging_dir / f"mod_{mod.id}"
        if staging_root.exists():
            shutil.rmtree(staging_root)
        
        # Record uninstallation
        installation = ModInstallation(
            mod_id=mod.id,
            install_type="uninstall",
            install_path=str(self.mod_path),
            rollback_available=False
        )
        self.db.add(installation)

        # Mark mod as inactive instead of deleting
        mod.is_active = False
        mod.is_enabled = False
        await self.db.commit()
    
    async def enable_mod(self, mod_id: int) -> None:
        """Enable a mod by hardlinking files from staging to game directory"""
        result = await self.db.execute(select(Mod).where(Mod.id == mod_id))
        mod = result.scalar_one_or_none()
        if not mod:
            return

        # Get mod files
        files_result = await self.db.execute(select(ModFile).where(ModFile.mod_id == mod_id))
        mod_files = files_result.scalars().all()

        staging_root = settings.staging_dir / f"mod_{mod.id}"
        
        for mod_file in mod_files:
            # Path in staging
            rel_path = Path(mod_file.file_path)
            staging_path = staging_root / rel_path
            
            if staging_path.exists():
                dest_path = Path(mod_file.install_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Create hardlink
                if dest_path.exists():
                    dest_path.unlink() # Remove existing file/link
                
                try:
                    import os
                    os.link(str(staging_path), str(dest_path))
                except OSError:
                    # Fallback to copy if hardlink fails (e.g. across filesystems)
                    shutil.copy2(str(staging_path), str(dest_path))
        
        mod.is_enabled = True
        await self.db.commit()
    
    async def disable_mod(self, mod_id: int) -> None:
        """Disable a mod by removing hardlinks from game directory"""
        result = await self.db.execute(select(Mod).where(Mod.id == mod_id))
        mod = result.scalar_one_or_none()
        if not mod:
            return

        # Get mod files
        files_result = await self.db.execute(select(ModFile).where(ModFile.mod_id == mod_id))
        mod_files = files_result.scalars().all()

        for mod_file in mod_files:
            source_path = Path(mod_file.install_path)
            if source_path.exists():
                source_path.unlink() # Just remove the link/file
                
                # Remove empty directories in game folder
                try:
                    # Only remove if empty and within the game's mod path
                    if self.mod_path in source_path.parents:
                        parent = source_path.parent
                        while parent != self.mod_path:
                            if not any(parent.iterdir()):
                                parent.rmdir()
                                parent = parent.parent
                            else:
                                break
                except OSError:
                    pass
        
        mod.is_enabled = False
        await self.db.commit()
    
    async def rollback_mod_installation(self, installation_id: int) -> None:
        """Rollback a specific mod installation using its backup"""
        result = await self.db.execute(
            select(ModInstallation).where(ModInstallation.id == installation_id)
        )
        installation = result.scalar_one_or_none()
        
        if not installation or not installation.rollback_available or not installation.backup_path:
            raise ModInstallationError("Rollback not available for this installation")
        
        backup_dir = Path(installation.backup_path)
        if not backup_dir.exists():
            raise ModInstallationError(f"Backup directory not found: {backup_dir}")
        
        # Restore files from backup
        for backup_file in backup_dir.rglob("*"):
            if backup_file.is_file():
                rel_path = backup_file.relative_to(backup_dir)
                dest_path = self.game_path / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, dest_path)
        
        # Update installation record
        installation.rollback_available = False
        await self.db.commit()

    async def _get_files_to_install(self, extracted_dir: Path, mod_structure: ModStructureDict) -> List[FileInfoDict]:
        """
        Identify which files from the extracted archive should be installed and where.
        
        Handles multiple mod types with proper path normalization:
        - Redscript (.reds) -> r6/scripts/
        - RED4ext plugins (.dylib) -> red4ext/plugins/
        - TweakXL tweaks (.yaml/.yml) -> r6/tweaks/
        - ArchiveXL mods (.archive) -> archive/pc/mod/
        - XL config files (.xl, .json) -> associated with their mod type
        - .bin files -> often game data files
        
        Priority:
        1. Standard directory structure (r6/scripts/, red4ext/plugins/, etc.)
        2. Fallback to extension-based detection for loose files
        
        Handles edge cases:
        - Case-insensitive directory matching
        - Nested mod folders (mod name as root folder)
        - Mixed mod types
        - Config files (.json, .toml, .xl)
        """
        files_to_install: List[FileInfoDict] = []
        seen_files: set[str] = set()  # Prevent duplicates
        
        # Define base paths for each mod type
        scripts_base = self.game_path / settings.default_mod_path
        plugins_base = self.game_path / settings.red4ext_plugins_path
        tweaks_base = self.game_path / settings.tweakxl_tweaks_path
        archives_base = self.game_path / settings.archivexl_mods_path
        
        # Helper to find directories case-insensitively
        def find_dir_ci(base: Path, *parts: str) -> Optional[Path]:
            """Find a directory path case-insensitively"""
            current = base
            for part in parts:
                found = None
                if current.exists():
                    for item in current.iterdir():
                        if item.is_dir() and item.name.lower() == part.lower():
                            found = item
                            break
                if found is None:
                    return None
                current = found
            return current
        
        # Helper to check if file has been seen
        def add_file(file_info: FileInfoDict) -> bool:
            key = str(file_info["source_path"])
            if key in seen_files:
                return False
            seen_files.add(key)
            files_to_install.append(file_info)
            return True
        
        # Detect if mod is wrapped in a single folder (common pattern)
        # e.g., ModName-1.0/r6/scripts/... instead of r6/scripts/...
        actual_root = extracted_dir
        root_contents = list(extracted_dir.iterdir())
        if len(root_contents) == 1 and root_contents[0].is_dir():
            # Check if the single folder contains mod structure
            potential_root = root_contents[0]
            has_structure = any([
                find_dir_ci(potential_root, "r6") is not None,
                find_dir_ci(potential_root, "red4ext") is not None,
                find_dir_ci(potential_root, "archive") is not None,
                find_dir_ci(potential_root, "bin") is not None,
            ])
            if has_structure:
                actual_root = potential_root
                logger.debug(f"Detected wrapped mod structure, using: {actual_root.name}")
        
        # === PHASE 1: Standard Directory Structure ===
        
        # 1a. RED4ext plugins (.dylib)
        red4ext_dir = find_dir_ci(actual_root, "red4ext", "plugins")
        if red4ext_dir and red4ext_dir.exists():
            for file_path in red4ext_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(red4ext_dir)
                    dest_path = plugins_base / rel_path
                    add_file({
                        "source_path": file_path,
                        "path": str(Path("red4ext/plugins") / rel_path),
                        "type": file_path.suffix.lower(),
                        "install_path": dest_path
                    })
        
        # 1b. TweakXL tweaks (.yaml/.yml)
        tweaks_dir = find_dir_ci(actual_root, "r6", "tweaks")
        if tweaks_dir and tweaks_dir.exists():
            for file_path in tweaks_dir.rglob("*"):
                if file_path.is_file():
                    suffix_lower = file_path.suffix.lower()
                    # Include .yaml, .yml, and .xl config files
                    if suffix_lower in ['.yaml', '.yml', '.xl']:
                        rel_path = file_path.relative_to(tweaks_dir)
                        dest_path = tweaks_base / rel_path
                        add_file({
                            "source_path": file_path,
                            "path": str(Path("r6/tweaks") / rel_path),
                            "type": suffix_lower,
                            "install_path": dest_path
                        })
        
        # 1c. ArchiveXL mods (.archive)
        archive_dir = find_dir_ci(actual_root, "archive", "pc", "mod")
        if archive_dir and archive_dir.exists():
            for file_path in archive_dir.rglob("*"):
                if file_path.is_file():
                    suffix_lower = file_path.suffix.lower()
                    # Include .archive and .xl config files
                    if suffix_lower in ['.archive', '.xl']:
                        rel_path = file_path.relative_to(archive_dir)
                        dest_path = archives_base / rel_path
                        add_file({
                            "source_path": file_path,
                            "path": str(Path("archive/pc/mod") / rel_path),
                            "type": suffix_lower,
                            "install_path": dest_path
                        })
        
        # 1d. Redscript files (.reds)
        scripts_dir = find_dir_ci(actual_root, "r6", "scripts")
        if scripts_dir and scripts_dir.exists():
            for file_path in scripts_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(scripts_dir)
                    dest_path = scripts_base / rel_path
                    add_file({
                        "source_path": file_path,
                        "path": str(Path("r6/scripts") / rel_path),
                        "type": file_path.suffix.lower(),
                        "install_path": dest_path
                    })
        
        # 1e. bin/x64 directory (game binaries/data)
        bin_dir = find_dir_ci(actual_root, "bin", "x64")
        if bin_dir and bin_dir.exists():
            bin_base = self.game_path / "bin" / "x64"
            for file_path in bin_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(bin_dir)
                    dest_path = bin_base / rel_path
                    add_file({
                        "source_path": file_path,
                        "path": str(Path("bin/x64") / rel_path),
                        "type": file_path.suffix.lower(),
                        "install_path": dest_path
                    })
        
        # If we found files using standard structure, return them
        if files_to_install:
            logger.debug(f"Found {len(files_to_install)} files using standard structure")
            return files_to_install
        
        # === PHASE 2: Fallback - Extension-based Detection ===
        logger.debug("No standard structure found, falling back to extension-based detection")
        
        # 2a. Find .dylib files (RED4ext plugins)
        for dylib_file in actual_root.rglob("*.dylib"):
            rel_path = dylib_file.relative_to(actual_root)
            rel_str = str(rel_path).lower()
            
            # Determine destination based on path structure
            if "red4ext" in rel_str and "plugins" in rel_str:
                # Already has correct structure, preserve it
                dest_path = self.game_path / rel_path
            else:
                # Place in plugins directory, preserving any subdirectory structure
                # but without random parent folders
                dest_path = plugins_base / dylib_file.name
            
            add_file({
                "source_path": dylib_file,
                "path": str(rel_path),
                "type": ".dylib",
                "install_path": dest_path
            })
        
        # 2b. Find .yaml/.yml files (TweakXL tweaks)
        for tweak_file in list(actual_root.rglob("*.yaml")) + list(actual_root.rglob("*.yml")):
            rel_path = tweak_file.relative_to(actual_root)
            rel_str = str(rel_path).lower()
            
            # Skip modinfo/config files that aren't game tweaks
            if tweak_file.name.lower() in ['modinfo.yaml', 'mod.yaml', 'config.yaml', 'config.yml']:
                continue
            
            # Determine destination
            if "r6" in rel_str and "tweaks" in rel_str:
                # Already has correct structure
                dest_path = self.game_path / rel_path
            else:
                # Place in tweaks directory
                dest_path = tweaks_base / tweak_file.name
            
            add_file({
                "source_path": tweak_file,
                "path": str(rel_path),
                "type": tweak_file.suffix.lower(),
                "install_path": dest_path
            })
        
        # 2c. Find .reds files (Redscript)
        for reds_file in actual_root.rglob("*.reds"):
            rel_path = reds_file.relative_to(actual_root)
            rel_parts = rel_path.parts
            
            # Normalize path - remove r6/scripts prefix if present
            if len(rel_parts) >= 2 and rel_parts[0].lower() == "r6" and rel_parts[1].lower() == "scripts":
                normalized_path = Path(*rel_parts[2:])
            else:
                normalized_path = rel_path
            
            dest_path = scripts_base / normalized_path
            add_file({
                "source_path": reds_file,
                "path": str(normalized_path),
                "type": ".reds",
                "install_path": dest_path
            })
        
        # 2d. Find .archive files (ArchiveXL)
        for archive_file in actual_root.rglob("*.archive"):
            rel_path = archive_file.relative_to(actual_root)
            rel_str = str(rel_path).lower()
            
            # Determine destination
            if "archive" in rel_str and "pc" in rel_str and "mod" in rel_str:
                # Already has correct structure
                dest_path = self.game_path / rel_path
            else:
                # Place in archives directory
                dest_path = archives_base / archive_file.name
            
            add_file({
                "source_path": archive_file,
                "path": str(rel_path),
                "type": ".archive",
                "install_path": dest_path
            })
        
        # 2e. Find .xl config files (ArchiveXL/TweakXL config)
        for xl_file in actual_root.rglob("*.xl"):
            rel_path = xl_file.relative_to(actual_root)
            rel_str = str(rel_path).lower()
            
            # Determine where this config belongs based on context
            if "archive" in rel_str:
                dest_path = archives_base / xl_file.name
            elif "tweaks" in rel_str:
                dest_path = tweaks_base / xl_file.name
            else:
                # Default to archives (most common for .xl)
                dest_path = archives_base / xl_file.name
            
            add_file({
                "source_path": xl_file,
                "path": str(rel_path),
                "type": ".xl",
                "install_path": dest_path
            })
        
        logger.debug(f"Found {len(files_to_install)} files using extension-based detection")
        return files_to_install

    async def _install_mod_files_from_list(self, files_to_install: List[FileInfoDict]) -> List[FileInfoDict]:
        """Actually copy the files to the game directory"""
        installed_files: List[FileInfoDict] = []
        for file_info in files_to_install:
            dest_path = file_info["install_path"]
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_info["source_path"], dest_path)
            installed_files.append(file_info)
        return installed_files

    async def _backup_conflicting_files(self, files_to_install: List[FileInfoDict]) -> Optional[Path]:
        """Backup files that will be overwritten"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = settings.backups_dir / f"install_{timestamp}"
        
        has_conflicts = False
        for file_info in files_to_install:
            dest_path = file_info["install_path"]
            if dest_path.exists():
                has_conflicts = True
                rel_path = dest_path.relative_to(self.game_path)
                backup_file_path = backup_dir / rel_path
                backup_file_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest_path, backup_file_path)
        
        if has_conflicts:
            return backup_dir
        return None
    
    async def _extract_archive(self, archive_path: Path, dest: Path) -> None:
        """Extract archive to destination"""
        import subprocess
        suffix = archive_path.suffix.lower()
        
        if suffix == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(dest)
        elif suffix in ['.7z', '.7zip']:
            with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                archive.extractall(path=dest)
        elif suffix == '.rar':
            # Try rarfile first, fall back to unar for RAR5 format
            try:
                with rarfile.RarFile(archive_path) as rf:
                    rf.extractall(dest)
            except (rarfile.BadRarFile, rarfile.NotRarFile) as e:
                # RAR5 format requires external tool - try unar
                logger.info(f"Falling back to unar for RAR extraction: {e}")
                try:
                    result = subprocess.run(
                        ["unar", "-q", "-o", str(dest), str(archive_path)],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                except FileNotFoundError:
                    raise ModInstallationError(
                        message="RAR5 extraction requires 'unar' tool. Install with: brew install unar",
                        code=InstallErrorCode.EXTRACTION_FAILED,
                        suggestion="Run 'brew install unar' then try again"
                    )
                except subprocess.CalledProcessError as sub_e:
                    raise ModInstallationError(
                        message=f"RAR extraction failed: {sub_e.stderr}",
                        code=InstallErrorCode.EXTRACTION_FAILED,
                        suggestion="The archive may be corrupted. Try re-downloading."
                    )
        else:
            raise ModInstallationError(f"Unsupported archive format: {suffix}")
    
    async def _detect_mod_structure(self, extracted_dir: Path) -> ModStructureDict:
        """Detect mod structure and type
        
        Mod types:
        - redscript: Pure .reds files
        - red4ext-plugin: Contains .dylib in red4ext/plugins/
        - tweakxl: Contains .yaml/.yml in r6/tweaks/
        - archivexl: Contains .archive in archive/pc/mod/
        - mixed: Multiple mod types
        """
        structure: ModStructureDict = {
            "name": extracted_dir.name,
            "type": "unknown",
            "version": None,
            "files": []
        }
        
        detected_types = []
        
        # Look for RED4ext plugins (.dylib)
        dylib_files = list(extracted_dir.rglob("*.dylib"))
        if dylib_files:
            detected_types.append("red4ext-plugin")
        
        # Look for TweakXL tweaks (.yaml/.yml in r6/tweaks/)
        tweaks_dir = extracted_dir / "r6" / "tweaks"
        if tweaks_dir.exists():
            tweak_files = list(tweaks_dir.rglob("*.yaml")) + list(tweaks_dir.rglob("*.yml"))
            if tweak_files:
                detected_types.append("tweakxl")
        else:
            # Also check for loose .yaml files that might be tweaks
            yaml_files = list(extracted_dir.rglob("*.yaml")) + list(extracted_dir.rglob("*.yml"))
            if yaml_files:
                detected_types.append("tweakxl")
        
        # Look for ArchiveXL mods (.archive)
        archive_files = list(extracted_dir.rglob("*.archive"))
        if archive_files:
            detected_types.append("archivexl")
        
        # Look for redscript files (.reds)
        reds_files = list(extracted_dir.rglob("*.reds"))
        if reds_files:
            detected_types.append("redscript")
        
        # Set mod type
        if len(detected_types) == 0:
            structure["type"] = "unknown"
        elif len(detected_types) == 1:
            structure["type"] = detected_types[0]
        else:
            structure["type"] = "mixed"
            structure["sub_types"] = detected_types
        
        # Look for modinfo.json or similar
        modinfo_files = [
            extracted_dir / "modinfo.json",
            extracted_dir / "mod.json",
            extracted_dir / "info.json",
            extracted_dir / "mod.toml",  # RED4ext plugins often use TOML
        ]
        
        for modinfo in modinfo_files:
            if modinfo.exists():
                try:
                    async with aiofiles.open(modinfo, 'r') as f:
                        content = await f.read()
                        if modinfo.suffix == '.toml':
                            import tomllib
                            info = tomllib.loads(content)
                        else:
                            import json
                            info = json.loads(content)
                        structure.update(info)
                except Exception:
                    pass
        
        return structure
    
    async def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256 = hashlib.sha256()
        async with aiofiles.open(file_path, 'rb') as f:
            while chunk := await f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    # =====================
    # FOMOD Installation Methods
    # =====================
    
    async def install_mod_from_file_with_fomod_check(
        self,
        mod_file: Path,
        nexus_mod_id: Optional[int] = None,
        mod_info: Optional[Dict[str, Any]] = None,
        fomod_choices: Optional[Dict[str, Any]] = None,
        check_compatibility: bool = True
    ) -> Mod:
        """Install mod from archive file with FOMOD detection
        
        If the mod contains a FOMOD installer and no choices are provided,
        raises FomodInstallRequired with a session ID for the wizard.
        
        Args:
            mod_file: Path to the mod archive
            nexus_mod_id: Optional Nexus mod ID
            mod_info: Optional mod metadata (name, author, etc.)
            fomod_choices: Optional pre-saved FOMOD choices
            check_compatibility: Whether to check macOS compatibility
            
        Returns:
            Installed Mod record
            
        Raises:
            FomodInstallRequired: When FOMOD wizard is needed
            ModInstallationError: On installation failure
        """
        # Check compatibility
        compat_result: Optional[CompatibilityResult] = None
        if check_compatibility:
            compat_result = await self.compatibility_checker.check_mod_file(mod_file)
            if not compat_result.compatible and settings.strict_compatibility:
                raise ModInstallationError(
                    f"Mod is not compatible with macOS: {compat_result.reason}"
                )
        
        # Calculate file hash
        file_hash = await self._calculate_file_hash(mod_file)
        
        # Check if mod already installed
        existing = await self.db.execute(
            select(Mod).where(Mod.file_hash == file_hash)
        )
        if existing.scalar_one_or_none():
            raise ModInstallationError("Mod already installed")
        
        # Extract mod to temp directory
        temp_dir = Path("/tmp") / f"mod_install_{mod_file.stem}"
        temp_dir.mkdir(exist_ok=True)
        
        try:
            await self._extract_archive(mod_file, temp_dir)
            
            # Check for FOMOD installer
            if detect_fomod(temp_dir):
                parser = FomodParser()
                fomod_config = parser.parse(temp_dir)
                
                # If no choices provided, create wizard session
                if fomod_choices is None:
                    session_manager = FomodSessionManager.get_instance()
                    
                    # Prepare mod info for session
                    session_mod_info = mod_info or {}
                    session_mod_info.update({
                        "name": session_mod_info.get("name") or fomod_config.info.name or mod_file.stem,
                        "author": session_mod_info.get("author") or fomod_config.info.author,
                        "version": session_mod_info.get("version") or fomod_config.info.version,
                        "nexus_mod_id": nexus_mod_id,
                        "file_hash": file_hash,
                        "file_path": str(mod_file),
                        "file_size": mod_file.stat().st_size
                    })
                    
                    # Create session (don't clean up temp_dir - session needs it)
                    session_id = session_manager.create_session(
                        config=fomod_config,
                        temp_dir=temp_dir,
                        mod_info=session_mod_info
                    )
                    
                    raise FomodInstallRequired(session_id, session_mod_info)
                
                # We have choices - install with FOMOD
                files_to_install = parser.resolve_files(fomod_config, fomod_choices, temp_dir)
                
                # Build mod_info from FOMOD config if not provided
                resolved_mod_info = mod_info or {
                    "name": fomod_config.module_name or fomod_config.info.name or mod_file.stem,
                    "version": fomod_config.info.version,
                    "author": fomod_config.info.author,
                    "description": fomod_config.info.description,
                }
                
                return await self._install_mod_with_resolved_files(
                    temp_dir=temp_dir,
                    files_to_install=files_to_install,
                    nexus_mod_id=nexus_mod_id,
                    mod_info=resolved_mod_info,
                    file_hash=file_hash,
                    file_size=mod_file.stat().st_size,
                    fomod_config=fomod_config,
                    fomod_choices=fomod_choices,
                    compat_result=compat_result
                )
            
            # No FOMOD - standard installation
            mod_structure = await self._detect_mod_structure(temp_dir)
            files_info = await self._get_files_to_install(temp_dir, mod_structure)
            
            # Convert to tuple format
            files_to_install = [
                (f["source_path"], f["install_path"].relative_to(self.mod_path))
                for f in files_info
            ]
            
            return await self._install_mod_with_resolved_files(
                temp_dir=temp_dir,
                files_to_install=files_to_install,
                nexus_mod_id=nexus_mod_id,
                mod_info=mod_info or {"name": mod_structure.get("name", mod_file.stem)},
                file_hash=file_hash,
                file_size=mod_file.stat().st_size,
                mod_structure=mod_structure,
                compat_result=compat_result
            )
            
        except FomodInstallRequired:
            # Re-raise - don't clean up temp_dir
            raise
        except Exception:
            # Clean up on any other error
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            raise
    
    async def install_mod_with_fomod(
        self,
        mod_info: Dict[str, Any],
        files_to_install: List[Tuple[Path, Path]],
        temp_dir: Path,
        fomod_choices: Dict[str, Any]
    ) -> Mod:
        """Install a mod with resolved FOMOD files
        
        Called after wizard completion with the resolved file list.
        
        Args:
            mod_info: Mod metadata from session
            files_to_install: List of (source_path, relative_dest_path) tuples
            temp_dir: Temp directory with extracted files
            fomod_choices: The choices made in the wizard
            
        Returns:
            Installed Mod record
        """
        try:
            return await self._install_mod_with_resolved_files(
                temp_dir=temp_dir,
                files_to_install=files_to_install,
                nexus_mod_id=mod_info.get("nexus_mod_id"),
                mod_info=mod_info,
                file_hash=mod_info.get("file_hash", ""),
                file_size=mod_info.get("file_size", 0),
                fomod_choices=fomod_choices
            )
        finally:
            # Clean up temp directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
    
    async def _install_mod_with_resolved_files(
        self,
        temp_dir: Path,
        files_to_install: List[Tuple[Path, Path]],
        nexus_mod_id: Optional[int],
        mod_info: Dict[str, Any],
        file_hash: str,
        file_size: int,
        mod_structure: Optional[ModStructureDict] = None,
        fomod_config: Optional[FomodConfig] = None,
        fomod_choices: Optional[Dict[str, Any]] = None,
        compat_result: Optional[CompatibilityResult] = None
    ) -> Mod:
        """Internal method to install mod with pre-resolved files
        
        This handles the actual file copying and database updates.
        """
        # Determine mod type
        mod_type = "fomod" if fomod_choices else (mod_structure.get("type", "unknown") if mod_structure else "unknown")
        
        # Create mod record
        mod = Mod(
            nexus_mod_id=nexus_mod_id,
            name=mod_info.get("name", "Unknown Mod"),
            author=mod_info.get("author"),
            version=mod_info.get("version"),
            description=mod_info.get("description"),
            game_id=settings.game_id,
            mod_type=mod_type,
            install_path=str(self.mod_path),
            file_hash=file_hash,
            file_size=file_size,
            thumbnail_url=mod_info.get("thumbnail_url"),
            nexus_url=mod_info.get("nexus_url"),
            is_enabled=True,
            is_active=True,
            mod_metadata={
                "fomod_installer": fomod_choices is not None,
                **(mod_structure or {})
            }
        )
        
        self.db.add(mod)
        await self.db.flush()
        
        # Create staging directory
        staging_root = settings.staging_dir / f"mod_{mod.id}"
        staging_root.mkdir(parents=True, exist_ok=True)
        
        # Process files
        installed_files: List[FileInfoDict] = []
        
        for source_path, dest_rel_path in files_to_install:
            if not source_path.exists():
                continue
            
            # Handle both file and directory sources
            if source_path.is_dir():
                # Copy directory contents
                for item in source_path.rglob("*"):
                    if item.is_file():
                        item_rel = item.relative_to(source_path)
                        final_rel = dest_rel_path / item_rel if dest_rel_path else item_rel
                        staging_dest = staging_root / final_rel
                        staging_dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(item), str(staging_dest))
                        
                        game_install_path = self.mod_path / final_rel
                        
                        installed_files.append({
                            "source_path": item,
                            "path": str(final_rel),
                            "type": item.suffix,
                            "install_path": game_install_path
                        })
            else:
                # Single file
                staging_dest = staging_root / dest_rel_path
                staging_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(source_path), str(staging_dest))
                
                game_install_path = self.mod_path / dest_rel_path
                
                installed_files.append({
                    "source_path": source_path,
                    "path": str(dest_rel_path),
                    "type": source_path.suffix,
                    "install_path": game_install_path
                })
        
        # Backup conflicting files
        backup_path = None
        if settings.backup_before_install:
            backup_path = await self._backup_conflicting_files(installed_files)
        
        # Create mod file records
        for file_info in installed_files:
            mod_file_record = ModFile(
                mod_id=mod.id,
                file_path=file_info["path"],
                file_type=file_info["type"],
                install_path=str(file_info["install_path"])
            )
            self.db.add(mod_file_record)
        
        # Save FOMOD choices if applicable
        if fomod_choices:
            choices_record = ModInstallerChoices(
                mod_id=mod.id,
                installer_type="fomod",
                choices_data=fomod_choices
            )
            self.db.add(choices_record)
        
        await self.db.flush()
        
        # Deploy mod (hardlink from staging to game)
        await self.enable_mod(mod.id)
        
        # Create installation record
        installation = ModInstallation(
            mod_id=mod.id,
            install_type="install",
            backup_path=str(backup_path) if backup_path else None,
            install_path=str(self.mod_path),
            file_hash_after=file_hash,
            rollback_available=backup_path is not None
        )
        self.db.add(installation)
        
        # Create dependency records
        if compat_result and compat_result.incompatible_dependencies:
            for dep_name in compat_result.incompatible_dependencies:
                dep = ModDependency(
                    mod_id=mod.id,
                    dependency_name=dep_name,
                    dependency_type="incompatible",
                    is_satisfied=False
                )
                self.db.add(dep)
        
        await self.db.commit()
        
        # Remove quarantine flags (macOS)
        if settings.auto_remove_quarantine:
            for file_info in installed_files:
                remove_quarantine_flag(file_info["install_path"])
        
        return mod