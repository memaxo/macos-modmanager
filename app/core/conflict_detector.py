from typing import List, Dict, Set, Optional
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.mod import Mod, ModFile
from app.models.compatibility import ModConflict
from dataclasses import dataclass
from enum import Enum


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
        self.mod_path = game_path / "r6/scripts"
    
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
        
        # Check mod dependencies for incompatible relationships
        deps1_result = await self.db.execute(
            select(ModDependency).where(
                ModDependency.mod_id == mod1.id,
                ModDependency.dependency_type == "incompatible"
            )
        )
        deps1 = deps1_result.scalars().all()
        
        for dep in deps1:
            # Check if mod2 matches the incompatible dependency
            if dep.target_mod_id == mod2.id or dep.target_nexus_mod_id == mod2.nexus_mod_id:
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
    
    async def get_conflicts_for_mod(self, mod_id: int) -> List[Dict]:
        """Get conflicts for a specific mod"""
        result = await self.db.execute(
            select(ModConflict).where(
                and_(
                    ModConflict.resolved == False,
                    (ModConflict.mod_id_1 == mod_id) | (ModConflict.mod_id_2 == mod_id)
                )
            )
        )
        conflicts = result.scalars().all()
        
        return [
            {
                "id": c.id,
                "file_path": c.file_path,
                "mod_id_1": c.mod_id_1,
                "mod_id_2": c.mod_id_2,
                "conflict_type": c.conflict_type,
                "severity": c.severity,
                "description": f"Conflict in {c.file_path}" if c.file_path else "Mod incompatibility"
            }
            for c in conflicts
        ]
    
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
