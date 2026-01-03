"""
Installation Validator for Cyberpunk 2077 macOS Mod Manager

Provides pre-flight validation, installation verification, and
error recovery for a hardened mod installation process.
"""

import os
import shutil
import subprocess
import psutil
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ValidationSeverity(Enum):
    """Severity level for validation issues"""
    ERROR = "error"      # Blocks installation
    WARNING = "warning"  # Allows but warns
    INFO = "info"        # Informational


@dataclass
class ValidationIssue:
    """Represents a single validation issue"""
    severity: ValidationSeverity
    code: str
    message: str
    suggestion: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of validation check"""
    passed: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    
    def add_error(self, code: str, message: str, suggestion: str, **details):
        self.issues.append(ValidationIssue(
            ValidationSeverity.ERROR, code, message, suggestion, details
        ))
        self.passed = False
    
    def add_warning(self, code: str, message: str, suggestion: str, **details):
        self.issues.append(ValidationIssue(
            ValidationSeverity.WARNING, code, message, suggestion, details
        ))
    
    def add_info(self, code: str, message: str, suggestion: str = "", **details):
        self.issues.append(ValidationIssue(
            ValidationSeverity.INFO, code, message, suggestion, details
        ))
    
    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [
                {
                    "severity": i.severity.value,
                    "code": i.code,
                    "message": i.message,
                    "suggestion": i.suggestion,
                    "details": i.details
                }
                for i in self.issues
            ]
        }


class InstallValidator:
    """Validates installation prerequisites and results"""
    
    # Minimum free space required (in bytes) - 500MB
    MIN_FREE_SPACE = 500 * 1024 * 1024
    
    # Game process names to check
    GAME_PROCESSES = ["Cyberpunk2077", "Cyberpunk 2077"]
    
    def __init__(self, game_path: Path):
        self.game_path = game_path
    
    async def pre_flight_check(
        self,
        archive_path: Optional[Path] = None,
        estimated_size: int = 0
    ) -> ValidationResult:
        """
        Run all pre-flight checks before installation.
        
        Args:
            archive_path: Path to the mod archive (optional)
            estimated_size: Estimated extracted size in bytes
            
        Returns:
            ValidationResult with all issues found
        """
        result = ValidationResult(passed=True)
        
        # Check game path exists
        self._check_game_path(result)
        
        # Check game is not running
        self._check_game_not_running(result)
        
        # Check disk space
        self._check_disk_space(result, estimated_size)
        
        # Check write permissions
        self._check_write_permissions(result)
        
        # Check archive (if provided)
        if archive_path:
            await self._check_archive(result, archive_path)
        
        # Check required directories exist
        self._check_mod_directories(result)
        
        return result
    
    def _check_game_path(self, result: ValidationResult) -> None:
        """Verify game installation path exists"""
        if not self.game_path.exists():
            result.add_error(
                code="GAME_NOT_FOUND",
                message=f"Game installation not found at {self.game_path}",
                suggestion="Verify the game is installed and the path is correct in Settings"
            )
            return
        
        # Check for game executable
        exe_path = self.game_path / "Cyberpunk2077.app"
        if not exe_path.exists():
            result.add_error(
                code="GAME_EXE_NOT_FOUND",
                message="Cyberpunk2077.app not found in game directory",
                suggestion="Verify this is the correct game installation directory"
            )
    
    def _check_game_not_running(self, result: ValidationResult) -> None:
        """Check if game is currently running"""
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] in self.GAME_PROCESSES:
                    result.add_error(
                        code="GAME_RUNNING",
                        message="Cyberpunk 2077 is currently running",
                        suggestion="Close the game before installing mods to prevent file conflicts",
                        pid=proc.pid
                    )
                    return
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    
    def _check_disk_space(self, result: ValidationResult, estimated_size: int) -> None:
        """Check available disk space"""
        try:
            disk_usage = shutil.disk_usage(self.game_path)
            required_space = max(self.MIN_FREE_SPACE, estimated_size * 2)  # 2x for safety
            
            if disk_usage.free < required_space:
                result.add_error(
                    code="INSUFFICIENT_DISK_SPACE",
                    message=f"Insufficient disk space. Need {required_space / 1024 / 1024:.0f}MB, have {disk_usage.free / 1024 / 1024:.0f}MB",
                    suggestion="Free up disk space or choose a different installation location",
                    required_mb=required_space / 1024 / 1024,
                    available_mb=disk_usage.free / 1024 / 1024
                )
            elif disk_usage.free < required_space * 2:
                result.add_warning(
                    code="LOW_DISK_SPACE",
                    message=f"Disk space is low ({disk_usage.free / 1024 / 1024:.0f}MB available)",
                    suggestion="Consider freeing up disk space for future mod installations"
                )
        except Exception as e:
            result.add_warning(
                code="DISK_CHECK_FAILED",
                message=f"Could not check disk space: {e}",
                suggestion="Ensure you have sufficient disk space before proceeding"
            )
    
    def _check_write_permissions(self, result: ValidationResult) -> None:
        """Check write permissions for mod directories"""
        test_dirs = [
            self.game_path / "r6" / "scripts",
            self.game_path / "r6" / "tweaks",
            self.game_path / "red4ext" / "plugins",
            self.game_path / "archive" / "pc" / "mod",
        ]
        
        for test_dir in test_dirs:
            if test_dir.exists():
                if not os.access(test_dir, os.W_OK):
                    result.add_error(
                        code="NO_WRITE_PERMISSION",
                        message=f"No write permission for {test_dir.relative_to(self.game_path)}",
                        suggestion="Check folder permissions or run with appropriate privileges",
                        path=str(test_dir)
                    )
            else:
                # Try to create the directory
                try:
                    test_dir.mkdir(parents=True, exist_ok=True)
                except PermissionError:
                    result.add_error(
                        code="CANNOT_CREATE_DIR",
                        message=f"Cannot create directory {test_dir.relative_to(self.game_path)}",
                        suggestion="Check parent folder permissions",
                        path=str(test_dir)
                    )
    
    async def _check_archive(self, result: ValidationResult, archive_path: Path) -> None:
        """Validate the mod archive"""
        if not archive_path.exists():
            result.add_error(
                code="ARCHIVE_NOT_FOUND",
                message=f"Archive file not found: {archive_path.name}",
                suggestion="Verify the file was uploaded correctly"
            )
            return
        
        # Check file size
        file_size = archive_path.stat().st_size
        if file_size == 0:
            result.add_error(
                code="EMPTY_ARCHIVE",
                message="Archive file is empty",
                suggestion="Re-download the mod file"
            )
            return
        
        # Validate archive format
        suffix = archive_path.suffix.lower()
        if suffix not in ['.zip', '.7z', '.7zip', '.rar']:
            result.add_error(
                code="UNSUPPORTED_FORMAT",
                message=f"Unsupported archive format: {suffix}",
                suggestion="Supported formats: .zip, .7z, .rar"
            )
            return
        
        # Try to open and validate the archive
        try:
            if suffix == '.zip':
                import zipfile
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    # Test archive integrity
                    bad_file = zf.testzip()
                    if bad_file:
                        result.add_error(
                            code="CORRUPT_ARCHIVE",
                            message=f"Archive is corrupted. Bad file: {bad_file}",
                            suggestion="Re-download the mod file"
                        )
                    elif len(zf.namelist()) == 0:
                        result.add_error(
                            code="EMPTY_ARCHIVE",
                            message="Archive contains no files",
                            suggestion="Verify this is the correct mod file"
                        )
            elif suffix in ['.7z', '.7zip']:
                import py7zr
                with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                    if len(archive.getnames()) == 0:
                        result.add_error(
                            code="EMPTY_ARCHIVE",
                            message="Archive contains no files",
                            suggestion="Verify this is the correct mod file"
                        )
            elif suffix == '.rar':
                import rarfile
                with rarfile.RarFile(archive_path) as rf:
                    if len(rf.namelist()) == 0:
                        result.add_error(
                            code="EMPTY_ARCHIVE",
                            message="Archive contains no files",
                            suggestion="Verify this is the correct mod file"
                        )
        except Exception as e:
            result.add_error(
                code="ARCHIVE_READ_ERROR",
                message=f"Cannot read archive: {str(e)}",
                suggestion="The archive may be corrupted. Try re-downloading."
            )
    
    def _check_mod_directories(self, result: ValidationResult) -> None:
        """Ensure mod directories exist or can be created"""
        required_dirs = [
            ("r6/scripts", "Redscript mods"),
            ("r6/tweaks", "TweakXL tweaks"),
            ("red4ext/plugins", "RED4ext plugins"),
            ("archive/pc/mod", "ArchiveXL mods"),
        ]
        
        for rel_path, description in required_dirs:
            full_path = self.game_path / rel_path
            if not full_path.exists():
                try:
                    full_path.mkdir(parents=True, exist_ok=True)
                    result.add_info(
                        code="DIR_CREATED",
                        message=f"Created {description} directory: {rel_path}",
                        path=str(full_path)
                    )
                except Exception as e:
                    result.add_warning(
                        code="DIR_CREATE_FAILED",
                        message=f"Could not create {description} directory: {e}",
                        suggestion=f"Manually create: {full_path}"
                    )
    
    async def post_install_verify(
        self,
        installed_files: List[Dict[str, Any]],
        mod_name: str
    ) -> ValidationResult:
        """
        Verify installation was successful.
        
        Args:
            installed_files: List of file info dicts with 'install_path'
            mod_name: Name of the mod for error messages
            
        Returns:
            ValidationResult with any issues found
        """
        result = ValidationResult(passed=True)
        
        missing_files = []
        permission_issues = []
        quarantine_files = []
        
        for file_info in installed_files:
            install_path = Path(file_info.get("install_path", ""))
            
            if not install_path.exists():
                missing_files.append(str(install_path))
                continue
            
            # Check permissions
            if not os.access(install_path, os.R_OK):
                permission_issues.append(str(install_path))
            
            # Check for quarantine flag (macOS)
            if self._has_quarantine_flag(install_path):
                quarantine_files.append(str(install_path))
        
        if missing_files:
            result.add_error(
                code="MISSING_FILES",
                message=f"{len(missing_files)} file(s) not found after installation",
                suggestion="Try reinstalling the mod",
                files=missing_files[:5]  # Limit to first 5
            )
        
        if permission_issues:
            result.add_warning(
                code="PERMISSION_ISSUES",
                message=f"{len(permission_issues)} file(s) have permission issues",
                suggestion="Check file permissions",
                files=permission_issues[:5]
            )
        
        if quarantine_files:
            result.add_warning(
                code="QUARANTINE_FLAGS",
                message=f"{len(quarantine_files)} file(s) still have quarantine flags",
                suggestion="Run: xattr -d com.apple.quarantine on the affected files",
                files=quarantine_files[:5]
            )
        
        if result.passed:
            result.add_info(
                code="INSTALL_SUCCESS",
                message=f"Successfully installed {mod_name} ({len(installed_files)} files)",
                file_count=len(installed_files)
            )
        
        return result
    
    def _has_quarantine_flag(self, path: Path) -> bool:
        """Check if file has macOS quarantine attribute"""
        try:
            result = subprocess.run(
                ["xattr", "-l", str(path)],
                capture_output=True,
                text=True
            )
            return "com.apple.quarantine" in result.stdout
        except Exception:
            return False
    
    async def remove_quarantine_flags(
        self,
        files: List[Path],
        verify: bool = True
    ) -> Tuple[int, int]:
        """
        Remove quarantine flags from files.
        
        Args:
            files: List of file paths
            verify: Whether to verify removal
            
        Returns:
            Tuple of (successful, failed) counts
        """
        successful = 0
        failed = 0
        
        for file_path in files:
            try:
                subprocess.run(
                    ["xattr", "-d", "com.apple.quarantine", str(file_path)],
                    check=True,
                    capture_output=True
                )
                
                if verify and self._has_quarantine_flag(file_path):
                    failed += 1
                else:
                    successful += 1
            except subprocess.CalledProcessError:
                # File might not have quarantine flag
                successful += 1
            except Exception:
                failed += 1
        
        return successful, failed


class AtomicInstaller:
    """
    Provides atomic installation with automatic rollback on failure.
    
    Features:
    - Stages files before committing
    - Backs up existing files that will be overwritten
    - Automatically rolls back on exception
    - Tracks created directories for cleanup
    - Supports hardlinks with copy fallback
    
    Usage:
        async with AtomicInstaller(game_path) as installer:
            for file_info in files:
                await installer.stage_file(file_info)
            await installer.commit()  # Or rollback automatically on exception
    """
    
    def __init__(
        self, 
        game_path: Path, 
        backup_dir: Optional[Path] = None,
        use_hardlinks: bool = True
    ):
        self.game_path = game_path
        self.backup_dir = backup_dir or Path("/tmp") / f"mod_backup_{os.getpid()}_{id(self)}"
        self.use_hardlinks = use_hardlinks
        self.staged_files: List[Tuple[Path, Path]] = []  # (source, dest)
        self.backed_up_files: List[Tuple[Path, Path]] = []  # (original, backup)
        self.deployed_files: List[Path] = []  # Files actually written
        self.created_dirs: List[Path] = []
        self.committed = False
        self._rollback_errors: List[str] = []
    
    async def __aenter__(self):
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and not self.committed:
            # Exception occurred - rollback
            await self.rollback()
        
        # Cleanup backup dir if commit was successful
        if self.committed and self.backup_dir.exists():
            shutil.rmtree(self.backup_dir, ignore_errors=True)
        
        return False  # Don't suppress exceptions
    
    async def stage_file(
        self,
        source: Path,
        dest: Path,
        backup_existing: bool = True
    ) -> None:
        """
        Stage a file for installation.
        
        Args:
            source: Source file path
            dest: Destination path in game directory
            backup_existing: Whether to backup existing file
        """
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        
        # Create parent directories if needed
        if not dest.parent.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Track only new directories
            parent = dest.parent
            while parent != self.game_path and parent not in self.created_dirs:
                if not any(parent.iterdir()):
                    self.created_dirs.append(parent)
                parent = parent.parent
        
        # Backup existing file
        if backup_existing and dest.exists():
            try:
                rel_path = dest.relative_to(self.game_path)
            except ValueError:
                # dest is not under game_path, use name only
                rel_path = Path(dest.name)
            
            backup_path = self.backup_dir / rel_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, backup_path)
            self.backed_up_files.append((dest, backup_path))
        
        # Stage the file
        self.staged_files.append((source, dest))
    
    async def commit(self) -> List[Path]:
        """
        Commit all staged files to their destinations.
        
        Returns:
            List of deployed file paths
        
        Raises:
            Exception: If any file operation fails (triggers rollback)
        """
        try:
            for source, dest in self.staged_files:
                # Remove existing file if present
                if dest.exists():
                    dest.unlink()
                
                # Try hardlink first, then copy
                if self.use_hardlinks:
                    try:
                        os.link(str(source), str(dest))
                    except OSError:
                        # Fallback to copy (cross-filesystem, etc.)
                        shutil.copy2(source, dest)
                else:
                    shutil.copy2(source, dest)
                
                self.deployed_files.append(dest)
            
            self.committed = True
            return self.deployed_files
        except Exception:
            await self.rollback()
            raise
    
    async def rollback(self) -> List[str]:
        """
        Rollback all changes made during this installation.
        
        Returns:
            List of error messages encountered during rollback (empty if clean)
        """
        self._rollback_errors = []
        
        # Remove newly deployed files
        for dest in reversed(self.deployed_files):
            try:
                if dest.exists():
                    dest.unlink()
            except Exception as e:
                self._rollback_errors.append(f"Failed to remove {dest}: {e}")
        
        # Also remove any staged files that might have been partially deployed
        for source, dest in reversed(self.staged_files):
            if dest not in self.deployed_files:
                try:
                    if dest.exists():
                        dest.unlink()
                except Exception:
                    pass
        
        # Restore backed up files
        for original, backup in reversed(self.backed_up_files):
            try:
                if backup.exists():
                    original.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, original)
            except Exception as e:
                self._rollback_errors.append(f"Failed to restore {original}: {e}")
        
        # Remove created directories (only if empty)
        for dir_path in reversed(self.created_dirs):
            try:
                if dir_path.exists() and not any(dir_path.iterdir()):
                    dir_path.rmdir()
            except Exception:
                pass  # Non-critical
        
        # Cleanup backup directory
        try:
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir, ignore_errors=True)
        except Exception:
            pass
        
        return self._rollback_errors
    
    def get_staged_count(self) -> int:
        """Get count of staged files"""
        return len(self.staged_files)
    
    def get_deployed_count(self) -> int:
        """Get count of successfully deployed files"""
        return len(self.deployed_files)
    
    def get_backup_count(self) -> int:
        """Get count of backed up files"""
        return len(self.backed_up_files)
