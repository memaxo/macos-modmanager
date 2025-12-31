import asyncio
import shutil
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.mod import Mod, ModFile, ModDependency
from app.core.compatibility import CompatibilityChecker, CompatibilityResult
from app.core.nexus_api import NexusAPIClient, NexusAPIError
from app.utils.path_utils import remove_quarantine_flag, make_executable
from app.config import settings
import aiofiles
import zipfile
import py7zr
import rarfile


class ModInstallationError(Exception):
    """Exception raised during mod installation"""
    pass


class ModManager:
    """Manages mod installation, uninstallation, and updates"""
    
    def __init__(self, db: AsyncSession, game_path: Path):
        self.db = db
        self.game_path = game_path
        self.mod_path = game_path / settings.default_mod_path
        self.compatibility_checker = CompatibilityChecker()
        self.mod_path.mkdir(parents=True, exist_ok=True)
    
    async def install_mod_from_file(
        self,
        mod_file: Path,
        nexus_mod_id: Optional[int] = None,
        check_compatibility: bool = True
    ) -> Mod:
        """Install mod from archive file"""
        
        # Check compatibility
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
        
        # Extract mod
        temp_dir = Path("/tmp") / f"mod_install_{mod_file.stem}"
        temp_dir.mkdir(exist_ok=True)
        
        try:
            await self._extract_archive(mod_file, temp_dir)
            
            # Detect mod structure
            mod_structure = await self._detect_mod_structure(temp_dir)
            
            # Backup if enabled
            if settings.backup_before_install:
                await self._backup_conflicting_files(mod_structure)
            
            # Install files
            installed_files = await self._install_mod_files(temp_dir, mod_structure)
            
            # Create mod record
            mod = Mod(
                nexus_mod_id=nexus_mod_id,
                name=mod_structure.get("name", mod_file.stem),
                version=mod_structure.get("version"),
                game_id="cyberpunk2077",
                mod_type=mod_structure.get("type", "redscript"),
                install_path=str(self.mod_path),
                file_hash=file_hash,
                file_size=mod_file.stat().st_size,
                is_enabled=True,
                is_active=True,
                metadata=mod_structure
            )
            
            self.db.add(mod)
            await self.db.flush()
            
            # Create mod file records
            for file_info in installed_files:
                mod_file_record = ModFile(
                    mod_id=mod.id,
                    file_path=file_info["path"],
                    file_type=file_info["type"],
                    install_path=str(file_info["install_path"])
                )
                self.db.add(mod_file_record)
            
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
            
        finally:
            # Cleanup
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
    
    async def install_mod_from_nexus(
        self,
        nexus_mod_id: int,
        file_id: Optional[int] = None,
        check_compatibility: bool = True
    ) -> Mod:
        """Install mod from Nexus Mods"""
        
        async with NexusAPIClient() as nexus:
            # Get mod info
            mod_info = await nexus.get_mod("cyberpunk2077", nexus_mod_id)
            
            # Get mod files
            files_info = await nexus.get_mod_files("cyberpunk2077", nexus_mod_id)
            files = files_info.get("files", [])
            
            if not files:
                raise ModInstallationError("No files available for this mod")
            
            # Use specified file or latest
            target_file = next((f for f in files if f["file_id"] == file_id), files[0])
            
            # Download mod file
            download_info = await nexus.get_download_link(
                "cyberpunk2077",
                nexus_mod_id,
                target_file["file_id"]
            )
            
            download_url = download_info.get("URI")
            if not download_url:
                raise ModInstallationError("Could not get download URL")
            
            # Download to temp location
            temp_file = settings.cache_dir / f"{nexus_mod_id}_{target_file['file_id']}.zip"
            await nexus.download_file(download_url, temp_file)
            
            try:
                # Install from downloaded file
                return await self.install_mod_from_file(
                    temp_file,
                    nexus_mod_id=nexus_mod_id,
                    check_compatibility=check_compatibility
                )
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
        
        # Delete mod record (cascade will delete files and dependencies)
        await self.db.delete(mod)
        await self.db.commit()
    
    async def enable_mod(self, mod_id: int) -> None:
        """Enable a mod"""
        result = await self.db.execute(select(Mod).where(Mod.id == mod_id))
        mod = result.scalar_one_or_none()
        if mod:
            mod.is_enabled = True
            await self.db.commit()
    
    async def disable_mod(self, mod_id: int) -> None:
        """Disable a mod"""
        result = await self.db.execute(select(Mod).where(Mod.id == mod_id))
        mod = result.scalar_one_or_none()
        if mod:
            mod.is_enabled = False
            await self.db.commit()
    
    async def _extract_archive(self, archive_path: Path, dest: Path) -> None:
        """Extract archive to destination"""
        suffix = archive_path.suffix.lower()
        
        if suffix == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(dest)
        elif suffix in ['.7z', '.7zip']:
            with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                archive.extractall(path=dest)
        elif suffix == '.rar':
            with rarfile.RarFile(archive_path) as rf:
                rf.extractall(dest)
        else:
            raise ModInstallationError(f"Unsupported archive format: {suffix}")
    
    async def _detect_mod_structure(self, extracted_dir: Path) -> Dict[str, Any]:
        """Detect mod structure and type"""
        structure = {
            "name": extracted_dir.name,
            "type": "unknown",
            "version": None,
            "files": []
        }
        
        # Look for redscript files
        reds_files = list(extracted_dir.rglob("*.reds"))
        if reds_files:
            structure["type"] = "redscript"
        
        # Look for modinfo.json or similar
        modinfo_files = [
            extracted_dir / "modinfo.json",
            extracted_dir / "mod.json",
            extracted_dir / "info.json"
        ]
        
        for modinfo in modinfo_files:
            if modinfo.exists():
                try:
                    async with aiofiles.open(modinfo, 'r') as f:
                        content = await f.read()
                        import json
                        info = json.loads(content)
                        structure.update(info)
                except Exception:
                    pass
        
        return structure
    
    async def _install_mod_files(
        self,
        extracted_dir: Path,
        mod_structure: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Install mod files to game directory"""
        installed_files = []
        
        # Find all .reds files
        reds_files = list(extracted_dir.rglob("*.reds"))
        
        if not reds_files:
            # If no .reds files, check for r6/scripts structure
            scripts_dir = extracted_dir / "r6" / "scripts"
            if scripts_dir.exists():
                reds_files = list(scripts_dir.rglob("*.reds"))
                if not reds_files:
                    # Copy entire scripts directory structure
                    for file_path in scripts_dir.rglob("*"):
                        if file_path.is_file():
                            rel_path = file_path.relative_to(scripts_dir)
                            dest_path = self.mod_path / rel_path
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(file_path, dest_path)
                            installed_files.append({
                                "path": str(rel_path),
                                "type": file_path.suffix,
                                "install_path": dest_path
                            })
                    return installed_files
        
        # Install .reds files
        for reds_file in reds_files:
            rel_path = reds_file.relative_to(extracted_dir)
            # Remove r6/scripts prefix if present
            if rel_path.parts[:2] == ("r6", "scripts"):
                rel_path = Path(*rel_path.parts[2:])
            
            dest_path = self.mod_path / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(reds_file, dest_path)
            
            installed_files.append({
                "path": str(rel_path),
                "type": ".reds",
                "install_path": dest_path
            })
        
        return installed_files
    
    async def _backup_conflicting_files(self, mod_structure: Dict[str, Any]) -> None:
        """Backup files that will be overwritten"""
        # TODO: Implement backup logic
        pass
    
    async def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256 = hashlib.sha256()
        async with aiofiles.open(file_path, 'rb') as f:
            while chunk := await f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
