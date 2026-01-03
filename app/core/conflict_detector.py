from typing import List, Dict, Set, Optional, Any, TypedDict
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from app.models.mod import Mod, ModFile, ModDependency
from app.models.compatibility import ModConflict
from dataclasses import dataclass
from enum import Enum
from app.config import settings


class ConflictDetailDict(TypedDict, total=False):
    id: int
    file_path: str
    conflict_type: str
    severity: str
    mod1: Dict[str, Any]
    mod2: Dict[str, Any]

class ConflictType(Enum):
    FILE_OVERWRITE = "file_overwrite"
    LOAD_ORDER = "load_order"
    INCOMPATIBLE = "incompatible"


class ConflictSeverity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ConflictInfo:
    file_path: str
    mod_id_1: int
    mod_id_2: int
    conflict_type: ConflictType
    severity: ConflictSeverity
    description: str


class ConflictDetector:
    """Detect conflicts between installed mods"""
    
    def __init__(self, db: AsyncSession, game_path: Path):
        self.db = db
        self.game_path = game_path
        self.mod_path = game_path / settings.default_mod_path
    
    async def detect_conflicts(self, mod_id: Optional[int] = None) -> List[ConflictInfo]:
        """Detect conflicts for all mods or a specific mod"""
        if mod_id:
            return await self._detect_mod_conflicts(mod_id)
        else:
            return await self._detect_all_conflicts()
    
    async def _detect_all_conflicts(self) -> List[ConflictInfo]:
        """Detect conflicts between all installed mods"""
        result = await self.db.execute(
            select(Mod).where(
                Mod.is_active == True,
                Mod.is_enabled == True
            )
        )
        mods = result.scalars().all()
        
        conflicts = []
        mod_list = list(mods)
        
        # Check each pair of mods
        for i, mod1 in enumerate(mod_list):
            for mod2 in mod_list[i+1:]:
                mod_conflicts = await self._check_mod_pair_conflicts(mod1, mod2)
                conflicts.extend(mod_conflicts)
        
        return conflicts
    
    async def _detect_mod_conflicts(self, mod_id: int) -> List[ConflictInfo]:
        """Detect conflicts for a specific mod"""
        result = await self.db.execute(select(Mod).where(Mod.id == mod_id))
        mod = result.scalar_one_or_none()
        
        if not mod:
            return []
        
        # Get all other enabled mods
        other_mods_result = await self.db.execute(
            select(Mod).where(
                Mod.is_active == True,
                Mod.is_enabled == True,
                Mod.id != mod_id
            )
        )
        other_mods = other_mods_result.scalars().all()
        
        conflicts = []
        for other_mod in other_mods:
            mod_conflicts = await self._check_mod_pair_conflicts(mod, other_mod)
            conflicts.extend(mod_conflicts)
        
        return conflicts
    
    async def _check_mod_pair_conflicts(
        self,
        mod1: Mod,
        mod2: Mod
    ) -> List[ConflictInfo]:
        """Check for conflicts between two mods"""
        conflicts = []
        
        # Get files for both mods
        files1_result = await self.db.execute(
            select(ModFile).where(ModFile.mod_id == mod1.id)
        )
        files1 = {f.install_path: f for f in files1_result.scalars().all()}
        
        files2_result = await self.db.execute(
            select(ModFile).where(ModFile.mod_id == mod2.id)
        )
        files2 = {f.install_path: f for f in files2_result.scalars().all()}
        
        # Check for file path conflicts
        common_paths = set(files1.keys()) & set(files2.keys())
        
        for path in common_paths:
            if path:  # Skip None/empty paths
                conflicts.append(ConflictInfo(
                    file_path=path,
                    mod_id_1=mod1.id,
                    mod_id_2=mod2.id,
                    conflict_type=ConflictType.FILE_OVERWRITE,
                    severity=ConflictSeverity.WARNING,
                    description=f"Both '{mod1.name}' and '{mod2.name}' modify {path}"
                ))
        
        # Check for known incompatibilities (from compatibility rules)
        incompat_conflicts = await self._check_incompatibilities(mod1, mod2)
        conflicts.extend(incompat_conflicts)
        
        return conflicts
    
    async def _check_incompatibilities(
        self,
        mod1: Mod,
        mod2: Mod
    ) -> List[ConflictInfo]:
        """Check for known incompatibilities between mods"""
        conflicts = []
        
        # Check mod1 dependencies for incompatible relationships with mod2
        deps1_result = await self.db.execute(
            select(ModDependency).where(
                ModDependency.mod_id == mod1.id,
                ModDependency.dependency_type == "incompatible"
            )
        )
        deps1 = deps1_result.scalars().all()
        
        for dep in deps1:
            # Check if mod2 matches the incompatible dependency
            matches = False
            if dep.target_mod_id and dep.target_mod_id == mod2.id:
                matches = True
            elif dep.nexus_mod_id and dep.nexus_mod_id == mod2.nexus_mod_id:
                matches = True
            elif dep.dependency_name.lower() in mod2.name.lower():
                matches = True
                
            if matches:
                conflicts.append(ConflictInfo(
                    file_path="",
                    mod_id_1=mod1.id,
                    mod_id_2=mod2.id,
                    conflict_type=ConflictType.INCOMPATIBLE,
                    severity=ConflictSeverity.CRITICAL,
                    description=f"'{mod1.name}' is incompatible with '{mod2.name}'"
                ))
        
        return conflicts
    
    async def save_conflicts_to_db(self, conflicts: List[ConflictInfo]) -> None:
        """Save detected conflicts to database"""
        # Clear existing unresolved conflicts
        await self.db.execute(
            select(ModConflict).where(ModConflict.resolved == False)
        )
        
        # Save new conflicts
        for conflict in conflicts:
            # Check if conflict already exists
            existing = await self.db.execute(
                select(ModConflict).where(
                    and_(
                        ModConflict.mod_id_1 == conflict.mod_id_1,
                        ModConflict.mod_id_2 == conflict.mod_id_2,
                        ModConflict.file_path == conflict.file_path,
                        ModConflict.resolved == False
                    )
                )
            )
            
            if not existing.scalar_one_or_none():
                db_conflict = ModConflict(
                    file_path=conflict.file_path,
                    mod_id_1=conflict.mod_id_1,
                    mod_id_2=conflict.mod_id_2,
                    conflict_type=conflict.conflict_type.value,
                    severity=conflict.severity.value,
                    resolved=False
                )
                self.db.add(db_conflict)
        
        await self.db.commit()
    
    async def get_conflicts_for_mod(self, mod_id: int) -> List[Dict[str, Any]]:
        """Get conflicts for a specific mod with detailed info"""
        from sqlalchemy.orm import aliased
        Mod1 = aliased(Mod)
        Mod2 = aliased(Mod)
        
        result = await self.db.execute(
            select(ModConflict, Mod1.name.label("mod_name_1"), Mod2.name.label("mod_name_2"))
            .join(Mod1, ModConflict.mod_id_1 == Mod1.id)
            .join(Mod2, ModConflict.mod_id_2 == Mod2.id)
            .where(
                and_(
                    ModConflict.resolved == False,
                    (ModConflict.mod_id_1 == mod_id) | (ModConflict.mod_id_2 == mod_id)
                )
            )
        )
        conflicts = result.all()
        
        return [
            {
                "id": c.ModConflict.id,
                "file_path": c.ModConflict.file_path,
                "mod_id_1": c.ModConflict.mod_id_1,
                "mod_name_1": c.mod_name_1,
                "mod_id_2": c.ModConflict.mod_id_2,
                "mod_name_2": c.mod_name_2,
                "conflict_type": c.ModConflict.conflict_type,
                "severity": c.ModConflict.severity,
                "description": f"Conflict in {c.ModConflict.file_path}" if c.ModConflict.file_path else "Mod incompatibility",
                "detected_at": c.ModConflict.detected_at.strftime("%Y-%m-%d %H:%M") if c.ModConflict.detected_at else "Unknown"
            }
            for c in conflicts
        ]

    async def get_conflict_details(self, conflict_id: int) -> Optional[ConflictDetailDict]:
        """Get detailed info for a single conflict including file metadata"""
        from sqlalchemy.orm import aliased
        Mod1 = aliased(Mod)
        Mod2 = aliased(Mod)
        
        result = await self.db.execute(
            select(ModConflict, Mod1, Mod2)
            .join(Mod1, ModConflict.mod_id_1 == Mod1.id)
            .join(Mod2, ModConflict.mod_id_2 == Mod2.id)
            .where(ModConflict.id == conflict_id)
        )
        row = result.first()
        if not row:
            return None
            
        conflict, mod1, mod2 = row
        
        # Get file info if it's a file overwrite
        file_info_1 = None
        file_info_2 = None
        
        if conflict.conflict_type == ConflictType.FILE_OVERWRITE.value:
            f1_res = await self.db.execute(
                select(ModFile).where(ModFile.mod_id == mod1.id, ModFile.install_path == conflict.file_path)
            )
            f1 = f1_res.scalar_one_or_none()
            if f1:
                file_info_1 = {"size": f1.file_size, "hash": f1.file_hash}
                
            f2_res = await self.db.execute(
                select(ModFile).where(ModFile.mod_id == mod2.id, ModFile.install_path == conflict.file_path)
            )
            f2 = f2_res.scalar_one_or_none()
            if f2:
                file_info_2 = {"size": f2.file_size, "hash": f2.file_hash}
        
        return {
            "id": conflict.id,
            "file_path": conflict.file_path,
            "conflict_type": conflict.conflict_type,
            "severity": conflict.severity,
            "mod1": {
                "id": mod1.id,
                "name": mod1.name,
                "author": mod1.author,
                "version": mod1.version,
                "file_info": file_info_1
            },
            "mod2": {
                "id": mod2.id,
                "name": mod2.name,
                "author": mod2.author,
                "version": mod2.version,
                "file_info": file_info_2
            }
        }
    
    async def resolve_conflict(
        self,
        conflict_id: int,
        resolution_method: str
    ) -> None:
        """Mark a conflict as resolved"""
        result = await self.db.execute(
            select(ModConflict).where(ModConflict.id == conflict_id)
        )
        conflict = result.scalar_one_or_none()
        
        if conflict:
            conflict.resolved = True
            conflict.resolution_method = resolution_method
            await self.db.commit()
    
    async def preview_installation_conflicts(
        self,
        files_to_install: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Preview conflicts that would occur if files are installed.
        
        This checks against:
        1. Files already in the game directory (from other mods or game files)
        2. Files owned by other enabled mods in the database
        
        Args:
            files_to_install: List of dicts with 'install_path' keys
            
        Returns:
            Dict with conflict details and resolution options
        """
        conflicts = []
        warnings = []
        
        # Get all enabled mods' file paths
        result = await self.db.execute(
            select(ModFile, Mod.name)
            .join(Mod, ModFile.mod_id == Mod.id)
            .where(Mod.is_enabled == True, Mod.is_active == True)
        )
        existing_mod_files = {
            row.ModFile.install_path: {"mod_name": row.name, "mod_id": row.ModFile.mod_id}
            for row in result.all()
            if row.ModFile.install_path
        }
        
        for file_info in files_to_install:
            install_path = str(file_info.get("install_path", ""))
            
            if not install_path:
                continue
            
            # Check if another mod owns this file
            if install_path in existing_mod_files:
                owner = existing_mod_files[install_path]
                conflicts.append({
                    "file_path": install_path,
                    "type": "mod_conflict",
                    "severity": "warning",
                    "message": f"File conflicts with '{owner['mod_name']}'",
                    "existing_mod_id": owner["mod_id"],
                    "existing_mod_name": owner["mod_name"],
                    "resolution_options": [
                        {"id": "overwrite", "label": "Overwrite (new mod wins)", "description": "The new mod's file will replace the existing one"},
                        {"id": "skip", "label": "Skip this file", "description": "Keep the existing file from the other mod"},
                        {"id": "backup", "label": "Backup and overwrite", "description": "Backup existing file before overwriting"}
                    ]
                })
            # Check if file exists in game directory (not owned by any mod)
            elif Path(install_path).exists():
                warnings.append({
                    "file_path": install_path,
                    "type": "file_exists",
                    "severity": "info",
                    "message": "File already exists (not tracked by mod manager)",
                    "resolution_options": [
                        {"id": "overwrite", "label": "Overwrite", "description": "Replace the existing file"},
                        {"id": "backup", "label": "Backup and overwrite", "description": "Backup existing file before overwriting"}
                    ]
                })
        
        return {
            "has_conflicts": len(conflicts) > 0,
            "conflict_count": len(conflicts),
            "warning_count": len(warnings),
            "conflicts": conflicts,
            "warnings": warnings,
            "can_auto_resolve": all(c["severity"] != "critical" for c in conflicts),
            "recommended_action": "overwrite" if not conflicts else "review"
        }