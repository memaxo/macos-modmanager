"""
Backup Manager

Handles backup creation, restoration, and management.
"""

import asyncio
import hashlib
import json
import shutil
import tarfile
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from app.core.game_detector import detect_game_installations
from app.config import settings


class BackupType(str, Enum):
    """Types of backups"""
    FULL = "full"
    INCREMENTAL = "incremental"
    MOD_SPECIFIC = "mod_specific"
    PRE_INSTALL = "pre_install"
    PRE_UPDATE = "pre_update"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


@dataclass
class BackupManifest:
    """Manifest file for a backup"""
    backup_id: str
    name: str
    backup_type: BackupType
    created_at: str
    game_path: str
    files: List[Dict[str, Any]]
    total_size: int
    file_count: int
    checksums: Dict[str, str]
    game_version: Optional[str] = None
    red4ext_version: Optional[str] = None


@dataclass
class BackupInfo:
    """Information about a backup"""
    id: str
    name: str
    backup_type: BackupType
    path: Path
    size_bytes: int
    file_count: int
    created_at: datetime
    is_compressed: bool
    game_version: Optional[str] = None
    status: str = "completed"


@dataclass
class RestoreResult:
    """Result of a restore operation"""
    success: bool
    message: str
    files_restored: int
    errors: List[str] = field(default_factory=list)


class BackupManager:
    """
    Manages backup creation, restoration, and cleanup.
    
    Features:
    - Full and incremental backups
    - Compression support
    - Manifest with checksums
    - Integrity verification
    - Auto-cleanup of old backups
    """
    
    BACKUP_DIR_NAME = ".mod_backups"
    
    # Directories to back up
    BACKUP_PATHS = {
        "frameworks": ["red4ext"],
        "plugins": ["red4ext/plugins"],
        "scripts": ["r6/scripts"],
        "tweaks": ["r6/tweaks"],
        "archives": ["archive/pc/mod"],
        "configs": ["red4ext/config.ini", "red4ext/plugins/*/config.json"],
    }
    
    def __init__(self, game_path: Optional[Path] = None, backup_dir: Optional[Path] = None):
        self.game_path = game_path
        self._backup_dir = backup_dir
    
    async def _get_game_path(self) -> Path:
        """Get game path"""
        if self.game_path:
            return self.game_path
        
        installations = await detect_game_installations()
        if not installations:
            raise RuntimeError("Game installation not found")
        
        self.game_path = Path(installations[0]['path'])
        return self.game_path
    
    @property
    def backup_dir(self) -> Path:
        """Get backup directory"""
        if self._backup_dir:
            return self._backup_dir
        
        # Default to home directory
        return Path.home() / self.BACKUP_DIR_NAME / "cyberpunk2077"
    
    def _ensure_backup_dir(self):
        """Ensure backup directory exists"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_backup_id(self) -> str:
        """Generate unique backup ID"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async def create_backup(
        self,
        name: str,
        backup_type: BackupType = BackupType.MANUAL,
        include_frameworks: bool = True,
        include_plugins: bool = True,
        include_scripts: bool = True,
        include_tweaks: bool = True,
        include_archives: bool = False,
        compress: bool = True,
        on_progress: Optional[Callable[[str, float], None]] = None,
    ) -> BackupInfo:
        """
        Create a backup of mod files.
        
        Args:
            name: Human-readable backup name
            backup_type: Type of backup
            include_*: What to include in backup
            compress: Whether to compress the backup
            on_progress: Progress callback (message, percent)
            
        Returns:
            BackupInfo with details about the created backup
        """
        game_path = await self._get_game_path()
        self._ensure_backup_dir()
        
        backup_id = self._generate_backup_id()
        backup_path = self.backup_dir / backup_id
        backup_path.mkdir(parents=True)
        
        if on_progress:
            on_progress("Starting backup...", 0)
        
        # Collect files to back up
        files_to_backup = []
        
        paths_to_include = []
        if include_frameworks:
            paths_to_include.extend(self.BACKUP_PATHS["frameworks"])
        if include_plugins:
            paths_to_include.extend(self.BACKUP_PATHS["plugins"])
        if include_scripts:
            paths_to_include.extend(self.BACKUP_PATHS["scripts"])
        if include_tweaks:
            paths_to_include.extend(self.BACKUP_PATHS["tweaks"])
        if include_archives:
            paths_to_include.extend(self.BACKUP_PATHS["archives"])
        
        for rel_path in paths_to_include:
            full_path = game_path / rel_path
            if full_path.exists():
                if full_path.is_dir():
                    for file_path in full_path.rglob("*"):
                        if file_path.is_file():
                            files_to_backup.append(file_path)
                else:
                    files_to_backup.append(full_path)
        
        if not files_to_backup:
            # Nothing to back up
            shutil.rmtree(backup_path)
            raise RuntimeError("No files found to back up")
        
        if on_progress:
            on_progress(f"Found {len(files_to_backup)} files", 10)
        
        # Copy files
        checksums = {}
        total_size = 0
        
        for i, file_path in enumerate(files_to_backup):
            try:
                # Calculate relative path
                rel_path = file_path.relative_to(game_path)
                dest_path = backup_path / rel_path
                
                # Create destination directory
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                shutil.copy2(file_path, dest_path)
                
                # Calculate checksum
                checksum = self._calculate_checksum(file_path)
                checksums[str(rel_path)] = checksum
                
                total_size += file_path.stat().st_size
                
                if on_progress:
                    progress = 10 + (i / len(files_to_backup)) * 70
                    on_progress(f"Copying {rel_path.name}...", progress)
                    
            except Exception as e:
                print(f"Error backing up {file_path}: {e}")
        
        if on_progress:
            on_progress("Creating manifest...", 80)
        
        # Create manifest
        manifest = BackupManifest(
            backup_id=backup_id,
            name=name,
            backup_type=backup_type,
            created_at=datetime.now().isoformat(),
            game_path=str(game_path),
            files=[
                {
                    "path": str(f.relative_to(game_path)),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                }
                for f in files_to_backup
            ],
            total_size=total_size,
            file_count=len(files_to_backup),
            checksums=checksums,
        )
        
        manifest_path = backup_path / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest.__dict__, f, indent=2)
        
        # Compress if requested
        final_path = backup_path
        if compress:
            if on_progress:
                on_progress("Compressing backup...", 90)
            
            archive_path = backup_path.with_suffix('.tar.gz')
            with tarfile.open(archive_path, 'w:gz') as tar:
                tar.add(backup_path, arcname=backup_id)
            
            # Remove uncompressed directory
            shutil.rmtree(backup_path)
            final_path = archive_path
        
        if on_progress:
            on_progress("Backup complete!", 100)
        
        return BackupInfo(
            id=backup_id,
            name=name,
            backup_type=backup_type,
            path=final_path,
            size_bytes=total_size if not compress else final_path.stat().st_size,
            file_count=len(files_to_backup),
            created_at=datetime.now(),
            is_compressed=compress,
        )
    
    async def create_incremental(
        self,
        base_backup_id: str,
        on_progress: Optional[Callable[[str, float], None]] = None,
    ) -> BackupInfo:
        """Create incremental backup based on a previous backup"""
        # For now, create a full backup
        # TODO: Implement true incremental backups
        return await self.create_backup(
            name=f"Incremental_{datetime.now().strftime('%Y%m%d')}",
            backup_type=BackupType.INCREMENTAL,
            on_progress=on_progress,
        )
    
    async def restore(
        self,
        backup_id: str,
        create_pre_restore_backup: bool = True,
        on_progress: Optional[Callable[[str, float], None]] = None,
    ) -> RestoreResult:
        """
        Restore from a backup.
        
        Args:
            backup_id: ID of backup to restore
            create_pre_restore_backup: Create safety backup before restore
            on_progress: Progress callback
            
        Returns:
            RestoreResult with outcome
        """
        game_path = await self._get_game_path()
        errors = []
        files_restored = 0
        
        # Find backup
        backup_path = self.backup_dir / backup_id
        compressed_path = self.backup_dir / f"{backup_id}.tar.gz"
        
        is_compressed = compressed_path.exists()
        
        if not backup_path.exists() and not is_compressed:
            return RestoreResult(
                success=False,
                message=f"Backup not found: {backup_id}",
                files_restored=0
            )
        
        if on_progress:
            on_progress("Starting restore...", 0)
        
        # Create pre-restore backup if requested
        if create_pre_restore_backup:
            if on_progress:
                on_progress("Creating pre-restore backup...", 5)
            try:
                await self.create_backup(
                    name="Pre-restore safety backup",
                    backup_type=BackupType.PRE_UPDATE,
                    compress=True
                )
            except Exception as e:
                errors.append(f"Warning: Could not create pre-restore backup: {e}")
        
        # Extract if compressed
        if is_compressed:
            if on_progress:
                on_progress("Extracting backup...", 10)
            with tarfile.open(compressed_path, 'r:gz') as tar:
                tar.extractall(self.backup_dir)
            backup_path = self.backup_dir / backup_id
        
        # Load manifest
        manifest_path = backup_path / "manifest.json"
        if not manifest_path.exists():
            return RestoreResult(
                success=False,
                message="Backup manifest not found",
                files_restored=0
            )
        
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        if on_progress:
            on_progress("Verifying backup integrity...", 20)
        
        # Verify integrity
        for rel_path, expected_checksum in manifest.get('checksums', {}).items():
            file_path = backup_path / rel_path
            if file_path.exists():
                actual_checksum = self._calculate_checksum(file_path)
                if actual_checksum != expected_checksum:
                    errors.append(f"Checksum mismatch for {rel_path}")
        
        if on_progress:
            on_progress("Restoring files...", 30)
        
        # Restore files
        file_list = manifest.get('files', [])
        for i, file_info in enumerate(file_list):
            rel_path = file_info['path']
            src_path = backup_path / rel_path
            dest_path = game_path / rel_path
            
            try:
                if src_path.exists():
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dest_path)
                    files_restored += 1
            except Exception as e:
                errors.append(f"Error restoring {rel_path}: {e}")
            
            if on_progress:
                progress = 30 + (i / len(file_list)) * 60
                on_progress(f"Restoring {Path(rel_path).name}...", progress)
        
        # Cleanup if we extracted
        if is_compressed:
            shutil.rmtree(backup_path)
        
        if on_progress:
            on_progress("Restore complete!", 100)
        
        return RestoreResult(
            success=len(errors) == 0,
            message="Restore completed successfully" if not errors else f"Restore completed with {len(errors)} errors",
            files_restored=files_restored,
            errors=errors
        )
    
    async def verify_integrity(self, backup_id: str) -> Dict[str, Any]:
        """Verify backup integrity"""
        backup_path = self.backup_dir / backup_id
        compressed_path = self.backup_dir / f"{backup_id}.tar.gz"
        
        is_compressed = compressed_path.exists()
        
        if not backup_path.exists() and not is_compressed:
            return {"valid": False, "error": "Backup not found"}
        
        # Extract if needed
        temp_extracted = False
        if is_compressed:
            with tarfile.open(compressed_path, 'r:gz') as tar:
                tar.extractall(self.backup_dir)
            backup_path = self.backup_dir / backup_id
            temp_extracted = True
        
        try:
            manifest_path = backup_path / "manifest.json"
            if not manifest_path.exists():
                return {"valid": False, "error": "No manifest"}
            
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Verify checksums
            mismatches = []
            for rel_path, expected in manifest.get('checksums', {}).items():
                file_path = backup_path / rel_path
                if file_path.exists():
                    actual = self._calculate_checksum(file_path)
                    if actual != expected:
                        mismatches.append(rel_path)
                else:
                    mismatches.append(f"{rel_path} (missing)")
            
            return {
                "valid": len(mismatches) == 0,
                "file_count": manifest.get('file_count', 0),
                "total_size": manifest.get('total_size', 0),
                "mismatches": mismatches,
            }
            
        finally:
            if temp_extracted:
                shutil.rmtree(backup_path)
    
    async def list_backups(self) -> List[BackupInfo]:
        """List all available backups"""
        self._ensure_backup_dir()
        
        backups = []
        
        for item in self.backup_dir.iterdir():
            backup_id = item.stem
            is_compressed = item.suffix == '.gz'
            
            try:
                if is_compressed:
                    # Read manifest from archive
                    with tarfile.open(item, 'r:gz') as tar:
                        manifest_member = tar.getmember(f"{backup_id}/manifest.json")
                        f = tar.extractfile(manifest_member)
                        if f:
                            manifest = json.load(f)
                else:
                    manifest_path = item / "manifest.json"
                    if not manifest_path.exists():
                        continue
                    with open(manifest_path, 'r') as f:
                        manifest = json.load(f)
                
                backups.append(BackupInfo(
                    id=manifest['backup_id'],
                    name=manifest['name'],
                    backup_type=BackupType(manifest['backup_type']),
                    path=item,
                    size_bytes=item.stat().st_size if is_compressed else manifest['total_size'],
                    file_count=manifest['file_count'],
                    created_at=datetime.fromisoformat(manifest['created_at']),
                    is_compressed=is_compressed,
                    game_version=manifest.get('game_version'),
                ))
            except Exception as e:
                print(f"Error reading backup {item}: {e}")
        
        # Sort by creation date, newest first
        backups.sort(key=lambda b: b.created_at, reverse=True)
        
        return backups
    
    async def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup"""
        backup_path = self.backup_dir / backup_id
        compressed_path = self.backup_dir / f"{backup_id}.tar.gz"
        
        deleted = False
        
        if backup_path.exists():
            shutil.rmtree(backup_path)
            deleted = True
        
        if compressed_path.exists():
            compressed_path.unlink()
            deleted = True
        
        return deleted
    
    async def delete_old_backups(self, keep: int = 10) -> int:
        """Delete old backups, keeping the N most recent"""
        backups = await self.list_backups()
        
        if len(backups) <= keep:
            return 0
        
        deleted = 0
        for backup in backups[keep:]:
            if await self.delete_backup(backup.id):
                deleted += 1
        
        return deleted
    
    async def get_backup_size(self, backup_id: str) -> int:
        """Get size of a backup in bytes"""
        backup_path = self.backup_dir / backup_id
        compressed_path = self.backup_dir / f"{backup_id}.tar.gz"
        
        if compressed_path.exists():
            return compressed_path.stat().st_size
        
        if backup_path.exists():
            total = 0
            for f in backup_path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
            return total
        
        return 0
    
    async def get_total_storage_used(self) -> int:
        """Get total storage used by all backups"""
        self._ensure_backup_dir()
        
        total = 0
        for item in self.backup_dir.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        
        return total
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate MD5 checksum of a file"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
